from dataclasses import dataclass
from typing import Dict, List

from .paths import IDENTITY_FILE, STATE_FILE, MEMORY_FILE
from .utils import read_json, write_json, append_jsonl, now_iso


@dataclass
class BodyMap:
    required_attached: List[str]
    optional_attached: List[str]
    detached: List[str]


class Kernel:
    def __init__(self, logger, manifest: Dict):
        self.logger = logger
        self.manifest = manifest
        self.identity = read_json(IDENTITY_FILE, {'name': 'Unknown'})
        self.state = read_json(STATE_FILE, {})

    def body_map(self) -> BodyMap:
        required = []
        optional = []
        detached = []
        for organ in self.manifest['organs']:
            if organ['attached']:
                if organ['required']:
                    required.append(organ['name'])
                else:
                    optional.append(organ['name'])
            else:
                detached.append(organ['name'])
        return BodyMap(required, optional, detached)

    def awaken(self) -> str:
        body = self.body_map()
        self.identity['status'] = 'awake'
        self.state['last_boot'] = now_iso()
        self.state['status'] = 'awake'
        self.state['body_state'] = 'coherent' if not body.detached or all(o not in self.manifest['required_names'] for o in body.detached) else 'degraded'
        self.state.setdefault('notes', []).append('awakened with body manifest')
        write_json(IDENTITY_FILE, self.identity)
        write_json(STATE_FILE, self.state)
        append_jsonl(MEMORY_FILE, {
            'timestamp': now_iso(),
            'type': 'boot',
            'text': f"awakened with required={body.required_attached}, optional={body.optional_attached}, detached={body.detached}",
        })
        self.logger.event('info', f"{self.identity.get('name', 'Agent')} awakened.")
        return self.startup_summary(body)

    def startup_summary(self, body: BodyMap) -> str:
        name = self.identity.get('name', 'Agent')
        lines = [
            f'{name} is awake.',
            f'Required organs: {", ".join(body.required_attached) or "none"}',
            f'Optional organs: {", ".join(body.optional_attached) or "none"}',
            f'Detached organs: {", ".join(body.detached) or "none"}',
        ]
        return '\n'.join(lines)

    def interact(self, text: str) -> str:
        text = text.strip()
        append_jsonl(MEMORY_FILE, {'timestamp': now_iso(), 'type': 'input', 'text': text})
        low = text.lower()
        if low in {'body', 'bodymap', 'manifest'}:
            body = self.body_map()
            reply = self.startup_summary(body)
        elif low in {'status', 'health'}:
            reply = f"Status: {self.state.get('status', 'unknown')} | Body: {self.state.get('body_state', 'unknown')}"
        elif low in {'help', '?'}:
            reply = 'Commands: body, status, help, quit'
        else:
            reply = f"I heard: {text}"
        append_jsonl(MEMORY_FILE, {'timestamp': now_iso(), 'type': 'output', 'text': reply})
        return reply
