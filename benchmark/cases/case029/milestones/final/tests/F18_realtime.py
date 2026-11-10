# feature: F18
"""Acceptance of live Realtime conversations through a local WebSocket peer."""
import base64
import asyncio
import json

import pytest
from pydantic import BaseModel

from F18_helpers import realtime_connection
from _helpers import bounded
from velmora import GuardrailFunctionOutput, function_tool, output_guardrail
from velmora import ModelBehaviorError, UserError
from velmora.realtime import RealtimeAgent, RealtimeRunner, realtime_handoff
from velmora.realtime.model import RealtimePlaybackTracker
from velmora.realtime.openai_realtime import OpenAIRealtimeSIPModel
from velmora.realtime.model_inputs import RealtimeModelSendRawMessage
from velmora import tool_input_guardrail, tool_output_guardrail, ToolGuardrailFunctionOutput
from websockets.exceptions import ConnectionClosedError


@pytest.mark.asyncio
async def test_multimodal_incremental_delivery_and_connection_end():
    async with realtime_connection() as (session, peer, events, settings):
        await session.send_message('Describe the scene.')
        request = await peer.request('conversation.item.create')
        assert request['item']['content'] == [{'type': 'input_text', 'text': 'Describe the scene.'}]
        await peer.request('response.create')
        await peer.response('live')
        image = {'type': 'input_image', 'image_url': 'https://example.org/scene.png'}
        await session.send_message({'type': 'message', 'role': 'user', 'content': [image]})
        request = await peer.request('conversation.item.create', matches=lambda r: r['item']['content'][0]['type'] == 'input_image')
        assert request['item']['content'][0]['image_url'] == image['image_url']
        pcm = b'\x01\x00' * 240
        await session.send_audio(pcm)
        assert base64.b64decode((await peer.request('input_audio_buffer.append'))['audio']) == pcm
        # The response end is held by the caller until audio was consumed, with the socket open.
        await peer.audio('live', 'speech', pcm)
        assert await events.read_audio(len(pcm)) == pcm
        delivered = [item for item in events.seen if item.type == 'audio']
        assert all(item.audio.response_id == 'live' and (item.item_id, item.content_index) == ('speech', 0) for item in delivered)
        await peer.delta('live', 'speech', 'A quiet ')
        await peer.delta('live', 'speech', 'harbor.')
        await peer.item('speech', 'A quiet harbor.', audio=True)
        history = await events.until(lambda e: e.type in ('history_added', 'history_updated') and
                                    (e.item.item_id == 'speech' if e.type == 'history_added' else any(i.item_id == 'speech' for i in e.history)))
        item = history.item if history.type == 'history_added' else next(i for i in history.history if i.item_id == 'speech')
        assert item.content[0].transcript == 'A quiet harbor.'
        await peer.send('conversation.item.input_audio_transcription.completed', item_id='user-speech', content_index=0, transcript='Where is this?', usage={'type': 'duration', 'seconds': 1})
        added = await events.until(lambda e: e.type == 'history_added' and e.item.item_id == 'user-speech')
        assert added.item.content[0].text == 'Where is this?'
        await peer.audio('live', 'speech', b'\x02\x00' * 120)
        await peer.response('live', done=True)
        await peer.socket.close(code=1000)
        await events.rest()
        assert b''.join(e.audio.data for e in events.seen if e.type == 'audio') == pcm + b'\x02\x00' * 120
        assert any(e.type == 'agent_end' for e in events.seen)
    async with realtime_connection() as (session, peer, events, settings):
        await peer.audio('broken', 'before-failure', pcm)
        assert await events.read_audio(len(pcm)) == pcm
        peer.expected_close_code = 1011
        await peer.socket.close(code=1011, reason='Transport failure')
        with pytest.raises(ConnectionClosedError):
            await events.rest()

    async with realtime_connection(model=OpenAIRealtimeSIPModel(), call_id='existing-call') as (session, peer, events, settings):
        await session.send_message('Continue the phone conversation.')
        await peer.request('response.create')
        await peer.response('attached-call')
        await peer.audio('attached-call', 'phone-speech', pcm)
        assert await events.read_audio(len(pcm)) == pcm


@pytest.mark.asyncio
async def test_model_audio_settings_and_turn_controls():
    scenarios = [({}, 'gpt-realtime-2.1', {'type': 'server_vad', 'create_response': True}),
                 ({'model_name': 'gpt-realtime-mini', 'turn_detection': None}, 'gpt-realtime-mini', None)]
    for extra, model, turn_detection in scenarios:
        supplied = {'voice': 'coral', 'input_audio_format': 'g711_ulaw', 'output_audio_format': 'g711_alaw', **extra}
        if not extra:
            supplied['turn_detection'] = turn_detection
        async with realtime_connection(settings=supplied) as (session, peer, events, settings):
            assert settings['model'] == model
            assert settings['audio']['output']['voice'] == 'coral'
            assert settings['audio']['input']['format'] == {'type': 'audio/pcmu'}
            assert settings['audio']['output']['format'] == {'type': 'audio/pcma'}
            assert settings['audio']['input']['turn_detection'] == turn_detection
            await session.send_audio(b'\x00' * 160, commit=turn_detection is None)
            await peer.request('input_audio_buffer.append')
            if turn_detection is None:
                await peer.request('input_audio_buffer.commit')
                await peer.model.send_event(RealtimeModelSendRawMessage(message={'type': 'response.create'}))
                await peer.request('response.create')
                await peer.response('manual')
                await peer.response('manual', done=True)
                await events.until(lambda e: e.type == 'agent_end')
            else:
                # A server-detected turn is delivered without a manual client commit.
                await peer.response('automatic')
                await peer.audio('automatic', 'auto-audio', b'\x01' * 80)
                assert (await events.until(lambda e: e.type == 'audio')).audio.data == b'\x01' * 80
                assert not any(r['type'] == 'input_audio_buffer.commit' for r in peer.requests)
                await peer.response('automatic', done=True)
                await events.until(lambda e: e.type == 'agent_end')
            start = len(peer.requests)
            await session.send_message('Please continue.')
            await peer.request('conversation.item.create', after=start)
            await peer.request('response.create', after=start)


@pytest.mark.asyncio
async def test_unsupported_structured_final_output():
    async with realtime_connection(RealtimeAgent(name='Plain', instructions='Speak naturally.')) as (session, peer, events, settings):
        assert settings['instructions'] == 'Speak naturally.'
        await session.send_message('Hello.')
        await peer.request('response.create')
    class FinalAnswer(BaseModel):
        answer: str
    # Accept rejection during configuration or use; do not pin diagnostic wording.
    with pytest.raises((TypeError, UserError)):
        agent = RealtimeAgent(name='Structured', output_type=FinalAnswer)
        async with realtime_connection(agent) as (session, peer, events, settings):
            await session.send_message('Hello.')
            await peer.request('response.create')
            await peer.response('structured')
            await peer.item('structured-item', 'Hello.')
            await peer.response('structured', done=True)
            await events.until(lambda e: e.type == 'agent_end')


@pytest.mark.asyncio
async def test_live_tool_approval_rejection_and_tool_guardrails():
    effects = []
    @function_tool
    def publish(title: str) -> str:
        effects.append(title)
        return 'Published: ' + title
    @function_tool(is_enabled=False)
    def hidden() -> str:
        effects.append('hidden')
        return 'Disabled tool result.'
    agent = RealtimeAgent(name='Publisher', tools=[publish, hidden])
    async with realtime_connection(agent) as (session, peer, events, settings):
        assert {t['name'] for t in settings['tools']} == {'publish'}
        await peer.call('publish', 'direct', {'title': 'News'})
        output = await peer.request('conversation.item.create', matches=lambda r: r['item']['type'] == 'function_call_output')
        assert output['item']['call_id'] == 'direct'
        assert output['item']['output'] == 'Published: News'
        ended = await events.until(lambda e: e.type == 'tool_end')
        assert ended.tool.name == 'publish' and ended.output == 'Published: News'
        assert effects == ['News']
        # A model call naming the disabled tool must not execute it; a later enabled call
        # is processed after it, so its output bounds the disabled call's handling.
        start = len(peer.requests)
        await peer.call('hidden', 'disabled-call', {})
        await peer.call('publish', 'after-disabled', {'title': 'Sports'})
        await peer.request('conversation.item.create', after=start, matches=lambda r: r['item'].get('call_id') == 'after-disabled')
        assert effects == ['News', 'Sports']
        assert not any(r['type'] == 'conversation.item.create' and r['item'].get('output') == 'Disabled tool result.'
                       for r in peer.requests)
        effects.remove('Sports')
    publish.needs_approval = True
    async with realtime_connection(agent) as (session, peer, events, settings):
        await peer.call('publish', 'approved', {'title': 'Weather'})
        pending = await events.until(lambda e: e.type == 'tool_approval_required')
        assert pending.call_id == 'approved'
        assert json.loads(pending.arguments) == {'title': 'Weather'}
        assert effects == ['News']
        await session.approve_tool_call(pending.call_id)
        output = await peer.request('conversation.item.create', matches=lambda r: r['item']['type'] == 'function_call_output')
        assert output['item']['output'] == 'Published: Weather'
        assert effects == ['News', 'Weather']
        await peer.call('publish', 'rejected', {'title': 'Private'})
        pending = await events.until(lambda e: e.type == 'tool_approval_required' and e.call_id == 'rejected')
        await session.reject_tool_call(pending.call_id, rejection_message='Publication denied by editor.')
        output = await peer.request('conversation.item.create', matches=lambda r: r['item'].get('call_id') == 'rejected')
        assert output['item']['output'] == 'Publication denied by editor.'
        assert effects == ['News', 'Weather']
    @tool_input_guardrail
    def refuse_input(data):
        return ToolGuardrailFunctionOutput.reject_content('Blocked input.')
    @tool_output_guardrail
    def replace_output(data):
        return ToolGuardrailFunctionOutput.reject_content('Redacted output.')
    publish.needs_approval = False
    publish.tool_input_guardrails = [refuse_input]
    async with realtime_connection(agent) as (session, peer, events, settings):
        await peer.call('publish', 'blocked', {'title': 'Confidential'})
        output = await peer.request('conversation.item.create', matches=lambda r: r['item'].get('call_id') == 'blocked')
        assert output['item']['output'] == 'Blocked input.'
        assert effects == ['News', 'Weather']
    publish.tool_input_guardrails = []
    publish.tool_output_guardrails = [replace_output]
    async with realtime_connection(agent) as (session, peer, events, settings):
        await peer.call('publish', 'redacted', {'title': 'Draft'})
        output = await peer.request('conversation.item.create', matches=lambda r: r['item'].get('call_id') == 'redacted')
        assert output['item']['output'] == 'Redacted output.'
        assert effects == ['News', 'Weather', 'Draft']


@pytest.mark.asyncio
async def test_specialist_handoff_preserves_conversation_and_validates_arguments():
    class Ticket(BaseModel):
        subject: str
        priority: int
    delivered = []
    def accept(context, ticket: Ticket):
        delivered.append(ticket.model_dump())
    @function_tool
    def diagnose() -> str:
        return 'Diagnostics ready.'
    specialist = RealtimeAgent(name='Specialist', instructions='Investigate the incident.', tools=[diagnose])
    transfer = realtime_handoff(specialist, tool_name_override='escalate', input_type=Ticket, on_handoff=accept)
    initial = RealtimeAgent(name='Reception', instructions='Collect the issue.', handoffs=[transfer])
    async with realtime_connection(initial) as (session, peer, events, settings):
        await peer.item('earlier', 'Keep this conversation.')
        await events.until(lambda e: e.type == 'history_added')
        await peer.call('escalate', 'transfer', {'subject': 'Packet loss', 'priority': 2})
        handoff = await events.until(lambda e: e.type == 'handoff')
        assert (handoff.from_agent.name, handoff.to_agent.name) == ('Reception', 'Specialist')
        update = await peer.request('session.update', matches=lambda r: r['session']['instructions'] == 'Investigate the incident.')
        assert {t['name'] for t in update['session']['tools']} == {'diagnose'}
        assert delivered == [{'subject': 'Packet loss', 'priority': 2}]
        await peer.call('diagnose', 'diagnosis', {})
        output = await peer.request('conversation.item.create', matches=lambda r: r['item'].get('call_id') == 'diagnosis')
        assert output['item']['output'] == 'Diagnostics ready.'
        await events.until(lambda e: e.type == 'tool_end')
        histories = [e.history for e in events.seen if e.type == 'history_updated']
        assert any(any(i.item_id == 'earlier' and i.content[0].text == 'Keep this conversation.' for i in h) for h in histories)
    async with realtime_connection(initial) as (session, peer, events, settings):
        await peer.call('escalate', 'invalid-transfer', {'subject': 'Incomplete'})
        with pytest.raises(ModelBehaviorError):
            await events.until(lambda e: e.type == 'handoff')
        assert delivered == [{'subject': 'Packet loss', 'priority': 2}]
    with pytest.raises(TypeError):
        realtime_handoff(specialist, input_filter=lambda data: data)


@pytest.mark.asyncio
async def test_interrupt_uses_actual_playback_and_history_corrections():
    tracker = RealtimePlaybackTracker()
    async with realtime_connection(tracker=tracker, settings={'output_audio_format': 'pcm16'}) as (session, peer, events, settings):
        await peer.response('spoken')
        await peer.item('utterance', 'A complete generated sentence.', audio=True)
        added = await events.until(lambda e: e.type == 'history_added')
        assert added.item.item_id == 'utterance'
        await peer.audio('spoken', 'utterance', b'\x01\x00' * 24000)
        await events.until(lambda e: e.type == 'audio')
        tracker.on_play_ms('utterance', 0, 175)
        tracker.on_play_ms('utterance', 0, 50)
        await session.interrupt()
        interrupted = await events.until(lambda e: e.type == 'audio_interrupted')
        assert (interrupted.item_id, interrupted.content_index) == ('utterance', 0)
        truncate = await peer.request('conversation.item.truncate')
        assert (truncate['item_id'], truncate['content_index'], truncate['audio_end_ms']) == ('utterance', 0, 225)
        await peer.send('conversation.item.truncated', item_id='utterance', content_index=0, audio_end_ms=225)
        assert (await peer.request('conversation.item.retrieve'))['item_id'] == 'utterance'
        await peer.send('conversation.item.retrieved', item={'id': 'utterance', 'type': 'message', 'role': 'assistant',
                        'status': 'completed', 'content': [{'type': 'output_audio', 'transcript': 'A complete'}]})
        corrected = await events.until(lambda e: e.type == 'history_updated' and any(i.item_id == 'utterance' and i.content[0].transcript == 'A complete' for i in e.history))
        assert len([i for i in corrected.history if i.item_id == 'utterance']) == 1


@pytest.mark.asyncio
async def test_accumulated_output_guardrail_rejects_affected_audio():
    inspected = []
    @output_guardrail
    def policy(context, agent, text):
        inspected.append(text)
        return GuardrailFunctionOutput(output_info={'reason': 'restricted' if 'restricted' in text else 'allowed'}, tripwire_triggered='restricted' in text)
    @output_guardrail
    def permissive(context, agent, text):
        return GuardrailFunctionOutput(output_info='always allowed', tripwire_triggered=False)
    # Only the guardrail that rejected the output is reported as responsible.
    agent = RealtimeAgent(name='Guarded', output_guardrails=[permissive, policy])
    async with realtime_connection(agent, config={'guardrails_settings': {'debounce_text_length': 1}}) as (session, peer, events, settings):
        await peer.response('allowed')
        await peer.audio('allowed', 'safe', b'\x01\x00' * 240)
        assert (await events.until(lambda e: e.type == 'audio')).item_id == 'safe'
        await peer.delta('allowed', 'safe', 'ordinary speech')
        await peer.response('allowed', done=True)
        await events.until(lambda e: e.type == 'agent_end')
        await peer.response('denied')
        await peer.audio('denied', 'unsafe', b'\x02\x00' * 240)
        await events.until(lambda e: e.type == 'audio' and e.item_id == 'unsafe')
        await peer.delta('denied', 'unsafe', 'a restr')
        await peer.delta('denied', 'unsafe', 'icted message')
        tripped = await events.until(lambda e: e.type == 'guardrail_tripped')
        assert tripped.message == 'a restricted message' and tripped.message in inspected
        assert [r.guardrail.get_name() for r in tripped.guardrail_results] == ['policy']
        assert tripped.guardrail_results[0].output.tripwire_triggered is True
        assert (await peer.request('response.cancel'))['response_id'] == 'denied'
        await events.until(lambda e: e.type == 'audio_interrupted')
        boundary = len(events.seen)
        await peer.audio('denied', 'unsafe', b'\x03\x00' * 240)
        await peer.fence(events, 'after-denied-audio')
        assert not any(e.type == 'audio' and e.item_id == 'unsafe' for e in events.seen[boundary:])
        assert any('ordinary speech' == text for text in inspected)
        assert not any(e.type == 'guardrail_tripped' and 'ordinary' in e.message for e in events.seen)


@pytest.mark.asyncio
async def test_late_guardrail_interrupt_is_response_scoped_and_text_is_not_audio():
    for audio in (True, False):
        started, release = asyncio.Event(), asyncio.Event()
        inspected = []
        @output_guardrail
        async def delayed_policy(context, agent, text):
            inspected.append(text)
            if 'restricted' in text:
                started.set()
                await release.wait()
                return GuardrailFunctionOutput(output_info='rejected', tripwire_triggered=True)
            return GuardrailFunctionOutput(output_info='accepted', tripwire_triggered=False)
        agent = RealtimeAgent(name='Late verdict', output_guardrails=[delayed_policy])
        async with realtime_connection(agent, config={'guardrails_settings': {'debounce_text_length': 1}}) as (session, peer, events, settings):
            await peer.response('old')
            if audio:
                await peer.audio('old', 'old-item', b'\x01\x00' * 240, content_index=1)
                await events.until(lambda e: e.type == 'audio')
            await peer.delta('old', 'old-item', 'restr', audio=audio)
            await peer.delta('old', 'old-item', 'icted content', audio=audio)
            await bounded(started.wait())
            await peer.response('old', done=True)
            await events.until(lambda e: e.type == 'agent_end')
            await peer.response('new')
            await peer.audio('new', 'new-item', b'\x02\x00' * 240)
            assert (await events.until(lambda e: e.type == 'audio' and e.item_id == 'new-item')).audio.data == b'\x02\x00' * 240
            release.set()
            trip = await events.until(lambda e: e.type == 'guardrail_tripped')
            assert trip.message == 'restricted content'
            assert [r.guardrail.get_name() for r in trip.guardrail_results] == ['delayed_policy']
            if audio:
                interruption = await events.until(lambda e: e.type == 'audio_interrupted')
                assert (interruption.item_id, interruption.content_index) == ('old-item', 1)
            await peer.audio('new', 'new-item', b'\x03\x00' * 120)
            assert (await events.until(lambda e: e.type == 'audio' and e.audio.data == b'\x03\x00' * 120)).item_id == 'new-item'
            await peer.fence(events, 'verdict-settled')
            assert not any(r['type'] == 'response.cancel' for r in peer.requests)
            interruptions = [e for e in events.seen if e.type == 'audio_interrupted']
            assert [(e.item_id, e.content_index) for e in interruptions] == ([('old-item', 1)] if audio else [])


@pytest.mark.asyncio
async def test_response_usage_accumulates_and_sessions_are_isolated():
    @function_tool
    def status() -> str:
        return 'Service healthy.'
    @output_guardrail
    def event_policy(context, agent, text):
        return GuardrailFunctionOutput(output_info='policy decision', tripwire_triggered='restricted' in text)
    specialist = RealtimeAgent(name='Metered specialist', output_guardrails=[event_policy])
    transfer = realtime_handoff(specialist, tool_name_override='transfer')
    runner = RealtimeRunner(starting_agent=RealtimeAgent(name='Metered', tools=[status], handoffs=[transfer]),
                            config={'tracing_disabled': True, 'guardrails_settings': {'debounce_text_length': 1}})
    for session_index in range(2):
        async with realtime_connection(runner=runner) as (session, peer, events, settings):
            initial = next(event for event in events.seen if event.type == 'history_updated')
            assert initial.info.context.usage.total_tokens == 0
            total_input = total_output = 0
            for index, (input_tokens, output_tokens) in enumerate([(17, 9), (23, 12)]):
                response_id = f'response-{session_index}-{index}'
                await peer.response(response_id)
                await peer.audio(response_id, response_id, b'\x01\x00' * 24)
                await peer.send('response.output_audio.done', response_id=response_id, item_id=response_id, output_index=0, content_index=0)
                complete = await events.until(lambda e: e.type == 'audio_end')
                assert (complete.item_id, complete.content_index) == (response_id, 0)
                await peer.response(response_id, done=True, usage={'total_tokens': input_tokens + output_tokens,
                    'input_tokens': input_tokens, 'output_tokens': output_tokens})
                usage = await events.until(lambda e: e.type == 'raw_model_event' and e.data.type == 'usage')
                assert (usage.data.usage.input_tokens, usage.data.usage.output_tokens, usage.data.usage.total_tokens) == (input_tokens, output_tokens, input_tokens + output_tokens)
                end = await events.until(lambda e: e.type == 'agent_end')
                total_input += input_tokens
                total_output += output_tokens
                cumulative = end.info.context.usage
                assert (cumulative.requests, cumulative.input_tokens, cumulative.output_tokens, cumulative.total_tokens) == (index + 1, total_input, total_output, total_input + total_output)
            if session_index == 0:
                await peer.call('status', 'status-call', {})
                start = await events.until(lambda e: e.type == 'tool_start')
                assert start.tool.name == 'status' and json.loads(start.arguments) == {}
                end = await events.until(lambda e: e.type == 'tool_end')
                assert end.output == 'Service healthy.'
                await peer.call('transfer', 'handoff-call', {})
                moved = await events.until(lambda e: e.type == 'handoff')
                assert (moved.from_agent.name, moved.to_agent.name) == ('Metered', 'Metered specialist')
                await peer.response('guarded-text')
                await peer.delta('guarded-text', 'text-item', 'restricted text', audio=False)
                verdict = await events.until(lambda e: e.type == 'guardrail_tripped')
                assert [r.guardrail.get_name() for r in verdict.guardrail_results] == ['event_policy']
                assert (await peer.request('response.cancel'))['response_id'] == 'guarded-text'
            await peer.send('error', error={'type': 'invalid_request_error', 'code': 'invalid_event', 'message': 'Provider rejected the request.'})
            # Read model errors as their own public event, not as assistant text.
            async def find_error():
                async for event in events.iterator:
                    events.seen.append(event)
                    if event.type == 'error':
                        return event
                raise AssertionError('Missing model error event.')
            error = await bounded(find_error())
            assert error.error.code == 'invalid_event'
