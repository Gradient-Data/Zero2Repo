# feature: F09
"""Application model boundary and history content observations for delegation."""
from F01_helpers import RecordingModel


class DelegationModel(RecordingModel):
    async def get_response(self, system_instructions, input, model_settings, tools,
                           output_schema, handoffs, tracing, **kwargs):
        response = await super().get_response(system_instructions, input, model_settings,
            tools, output_schema, handoffs, tracing, **kwargs)
        self.requests[-1]["handoffs"] = list(handoffs)
        self.requests[-1]["settings"] = model_settings
        return response


def history_contents(items):
    """Read text content through Responses message carriers, without parsing prose."""
    contents = []
    for item in items:
        if "role" not in item:
            continue
        content = item["content"]
        if isinstance(content, str):
            contents.append(content)
        else:
            contents.extend(part["text"] for part in content
                            if part["type"] in ("input_text", "output_text"))
    return contents
