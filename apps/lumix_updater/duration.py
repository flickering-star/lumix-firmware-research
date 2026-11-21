"""Only the two reviewed model-specific duration edits; no address editor."""
from .download import sha
from .models import model_spec


def apply_duration(plain,component,model,plan):
    spec=model_spec(model);variant=plan.get('duration_variant','regional-only-v1')
    if variant not in ('regional-only-v1','regional-and-format-v2'):
        raise ValueError('The bundled duration variant is unsupported')
    changed=bytearray(plain)
    if component=='program':
        at=spec['duration_offset'];before=bytes.fromhex(spec['duration_before'])
        if plain[at:at+4]!=before:raise ValueError('The recording-policy wrapper differs')
        changed[at:at+4]=bytes.fromhex('00df0004')
    if component=='program2' and variant=='regional-and-format-v2':
        at=spec['format_duration_offset'];before=bytes.fromhex(spec['format_duration_before'])
        if plain[at:at+len(before)]!=before:raise ValueError('The format-duration selector differs')
        changed[at+3]=0xCA
    expected=(plan.get('duration_component_sha256',{}).get(component) if variant=='regional-and-format-v2' else
              plan.get('duration_target_sha256') if component=='program' else plan['components'][component]['target_sha256'])
    if expected is None or sha(changed)!=expected:
        raise ValueError('The recording-limit component does not match its reviewed target')
    return bytes(changed)
