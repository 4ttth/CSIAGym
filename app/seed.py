"""
app/seed.py
===========
Idempotent startup seeding of the official CSIA GYM challenge set.

Called once from :func:`app.create_app` after the schema is in place. On the
first boot it mints a flag per challenge, builds every artifact from the
sources in ``challenges/``, and inserts the rows. On every boot after that it
sees the challenges already exist and does nothing.

Flags
-----
Flags are **generated on the deployment**, never committed. Precedence:

1. ``SEED_FLAG_<SLUG_IN_CAPS_WITH_UNDERSCORES>`` in the environment
2. the value already recorded in ``instance/seed_flags.json``
3. a fresh ``CSIA{...}`` built from :func:`secrets.token_hex`

Launchable challenges (Web, Binary Exploitation) ship a ``flag.txt``, so the
runner overwrites it with a per-player flag at launch and the static value
below is only ever a fallback.

Operator notes
--------------
* ``SEED_CHALLENGES=0`` skips seeding entirely.
* ``instance/seed_flags.json`` is written 0600 and is the answer key for the
  challenges that are not per-player. Keep it off the projector.
* Re-running after you delete a challenge in the admin console will seed it
  again — that is the intended way to reset one.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import stat
import sys
import traceback

CHALLENGE_FILES_DIRNAME = 'challenge_files'
SEEDED_BUILD_DIRNAME = 'seeded'
FLAG_STORE_NAME = 'seed_flags.json'

#: Word-shaped flags read better on a projector than 64 hex characters, but the
#: entropy still has to be real, so a random suffix is always appended.
_FLAG_PREFIX = 'CSIA'


def _repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _instance_dir() -> str:
    path = os.path.join(_repo_root(), 'instance')
    os.makedirs(path, exist_ok=True)
    return path


def _env_key(slug: str) -> str:
    return 'SEED_FLAG_' + slug.replace('-', '_').upper()


def _mint_flag(slug: str) -> str:
    return f'{_FLAG_PREFIX}{{{slug.replace("-", "_")}_{secrets.token_hex(8)}}}'


def _load_flag_store(path: str) -> dict:
    try:
        with open(path) as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_flag_store(path: str, store: dict) -> None:
    tmp = path + '.tmp'
    with open(tmp, 'w') as fh:
        json.dump(store, fh, indent=2, sort_keys=True)
    os.replace(tmp, path)
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)   # 0600 — this is the answer key
    except OSError:
        pass


def _system_author(db, User):
    """
    Return the user that owns the official challenges.

    Prefers an existing admin so the challenges show up under a real person;
    falls back to a dedicated, login-disabled system account on a virgin
    database where nobody has registered yet.
    """
    admin = User.query.filter_by(is_admin=True).order_by(User.id).first()
    if admin:
        return admin

    system = User.query.filter_by(username='CSIA-GYM').first()
    if system:
        return system

    from werkzeug.security import generate_password_hash

    system = User(
        username='CSIA-GYM',
        email='gym@haucsia.com',
        password_hash=generate_password_hash(secrets.token_urlsafe(48)),
        is_admin=False,
    )
    # Not every deployment carries these columns; set them only if present.
    if hasattr(system, 'is_hidden_from_scoreboard'):
        system.is_hidden_from_scoreboard = True
    if hasattr(system, 'bio'):
        system.bio = 'Official challenge author. Not a player.'
    db.session.add(system)
    db.session.commit()
    return system


def _publish_attachment(src_path: str, slug: str) -> str:
    """
    Copy a built artifact into instance/challenge_files/ under a name that is
    unique per challenge, and return that name for Challenge.file_attachment.
    """
    dest_dir = os.path.join(_instance_dir(), CHALLENGE_FILES_DIRNAME)
    os.makedirs(dest_dir, exist_ok=True)
    stored = f'{slug}__{os.path.basename(src_path)}'
    shutil.copy2(src_path, os.path.join(dest_dir, stored))
    return stored


def seed_challenges(app) -> None:
    """Build and insert any official challenge that is not already present."""
    if os.environ.get('SEED_CHALLENGES', '1').strip().lower() in ('0', 'false', 'no'):
        app.logger.info('seed: SEED_CHALLENGES disabled, skipping.')
        return

    # Imported lazily so a broken challenge module can never stop the app booting.
    try:
        sys.path.insert(0, _repo_root())
        import challenges as challenge_pkg
        from app import db
        from app.models import Challenge, User, WebChallenge, NcChallenge, MiscChallenge
    except Exception:
        app.logger.error('seed: could not import the challenge set:\n%s', traceback.format_exc())
        return

    specs = challenge_pkg.all_specs()
    existing = {c.title for c in Challenge.query.with_entities(Challenge.title).all()}
    pending = [s for s in specs if s['title'] not in existing]
    if not pending:
        app.logger.info('seed: all %d official challenges already present.', len(specs))
        return

    author = _system_author(db, User)

    store_path = os.path.join(_instance_dir(), FLAG_STORE_NAME)
    store = _load_flag_store(store_path)
    build_root = os.path.join(_instance_dir(), SEEDED_BUILD_DIRNAME)
    os.makedirs(build_root, exist_ok=True)

    created = []
    for spec in pending:
        slug = spec['slug']
        flag = os.environ.get(_env_key(slug)) or store.get(slug) or _mint_flag(slug)

        try:
            ctx = challenge_pkg.BuildContext(flag, os.path.join(build_root, slug))
            built = spec['module'].build(ctx)
        except Exception:
            app.logger.error('seed: build failed for %s, skipping:\n%s',
                             slug, traceback.format_exc())
            continue

        store[slug] = built.get('flag') or flag

        challenge = Challenge(
            title=spec['title'],
            description=built['description'],
            category=spec['category'],
            difficulty=spec['difficulty'],
            points=spec['points'],
            flag=store[slug],
            is_regex=bool(built.get('is_regex')),
            author_id=author.id,
        )
        if built.get('attachment'):
            challenge.file_attachment = _publish_attachment(built['attachment'], slug)

        db.session.add(challenge)
        db.session.flush()   # assign challenge.id without ending the transaction

        if built.get('web_archive'):
            db.session.add(WebChallenge(challenge_id=challenge.id,
                                        archive_path=built['web_archive']))
        if built.get('nc_binary'):
            db.session.add(NcChallenge(challenge_id=challenge.id,
                                       binary_path=built['nc_binary']))
        if built.get('misc_file'):
            db.session.add(MiscChallenge(challenge_id=challenge.id,
                                         file_path=built['misc_file']))
        created.append((slug, spec['title'], spec['dynamic_flag']))

    if not created:
        db.session.rollback()
        app.logger.warning('seed: nothing could be built.')
        return

    db.session.commit()
    _save_flag_store(store_path, store)

    app.logger.info('seed: published %d challenge(s) as "%s".', len(created), author.username)
    for slug, title, dynamic in created:
        app.logger.info('seed:   %-20s %s%s', slug, title,
                        '  (per-player flag at launch)' if dynamic else '')
    app.logger.info('seed: static flags recorded in %s (mode 0600).', store_path)
