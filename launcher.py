#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import asdict

from velisara_agent.bootstrap import Bootstrapper
from velisara_agent.config.defaults import DEFAULT_CONFIG
from velisara_agent.daemons.caretaker import CaretakerDaemon
from velisara_agent.daemons.memory import MemoryDaemon
from velisara_agent.daemons.pulse import PulseDaemon
from velisara_agent.kernel import Kernel
from velisara_agent.logging_layer import EventLogger
from velisara_agent.organs.registry import ALL_ORGANS
from velisara_agent.paths import BOOT_LOG, EVENT_LOG, CONFIG_FILE
from velisara_agent.utils import read_json


def assemble_body(logger):
    config = read_json(CONFIG_FILE, DEFAULT_CONFIG)
    organ_results = []
    required_names = set(config['minimum_required_organs'])

    context = {'logger': logger, 'config': config}
    for organ in ALL_ORGANS:
        status = organ.attach(context)
        organ_results.append(asdict(status))
        logger.boot('info', f"Organ {status.name}: {'attached' if status.attached else 'detached'} — {status.message}")

    missing_required = [o['name'] for o in organ_results if o['required'] and not o['attached']]
    manifest = {
        'required_names': list(required_names),
        'organs': organ_results,
        'viable': not missing_required,
        'missing_required': missing_required,
    }
    return config, manifest


def run():
    logger = EventLogger(EVENT_LOG, BOOT_LOG)
    boot = Bootstrapper(logger)
    summary = []

    try:
        for step in [boot.ensure_layout, boot.acquire_lock, boot.ensure_defaults, boot.validate_required_files]:
            status = step()
            summary.extend(status.details)
            for detail in status.details:
                logger.boot('info' if status.ok else 'error', f'{status.phase}: {detail}')
            if not status.ok:
                print('Assembly mode only. Required substrate is incomplete.')
                for line in summary:
                    print('-', line)
                return

        config, manifest = assemble_body(logger)
        summary.extend([f"viable={manifest['viable']}", f"missing_required={manifest['missing_required']}"])
        boot.write_manifest(manifest)

        if not manifest['viable']:
            logger.boot('error', 'Embodiment check failed; refusing awakening.')
            print('Refusing awakening: minimum viable embodiment not met.')
            for organ in manifest['organs']:
                state = 'attached' if organ['attached'] else 'detached'
                print(f"- {organ['name']}: {state} ({organ['message']})")
            return

        kernel = Kernel(logger, manifest)
        context = {
            'logger': logger,
            'boot_summary': summary,
            'identity': kernel.identity,
        }
        daemons = [
            CaretakerDaemon(interval_seconds=15),
            MemoryDaemon(interval_seconds=config.get('snapshot_interval_seconds', 30)),
            PulseDaemon(interval_seconds=config.get('heartbeat_interval_seconds', 5)),
        ]
        for daemon in daemons:
            daemon.start(context)
            logger.boot('info', f'Daemon started: {daemon.name}')

        print(kernel.awaken())
        if config.get('interactive_shell', True):
            while True:
                try:
                    text = input('vel> ').strip()
                except (EOFError, KeyboardInterrupt):
                    print('\nShutting down.')
                    break
                if text.lower() in {'quit', 'exit'}:
                    print('Goodbye.')
                    break
                print(kernel.interact(text))
    finally:
        boot.release_lock()


if __name__ == '__main__':
    run()
