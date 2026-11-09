# feature: F19
"""Acceptance checks for speech workflows through public voice entries."""
import asyncio
import json

import numpy as np
import pytest
from openai import AsyncOpenAI
from F01_helpers import function_call
from F03_helpers import tool_trace_destination
from F09_helpers import history_contents
from F19_helpers import (SpeechWorkflow, speech_provider, transcription_socket, voice_events,
                         speech_samples, voice_order, ApplicationSTT, ApplicationTTS,
                         TurnSession, ApplicationVoiceProvider, VoiceStreamModel,
                         synthesis_requests, text_samples, repeated_samples)
from _helpers import consume, Observation
from velmora import Agent, FunctionTool, handoff, UserError
from velmora.voice import (AudioInput, StreamedAudioInput, VoicePipeline, VoicePipelineConfig,
                          STTModelSettings, TTSModelSettings, SingleAgentVoiceWorkflow)
from velmora.voice.models.openai_model_provider import OpenAIVoiceModelProvider


@pytest.mark.asyncio
async def test_f19_t01():
    source = np.array([-903, 17, 28011, -14002], dtype=np.int16)
    workflow = SpeechWorkflow()
    async with speech_provider(transcript='The green suitcase') as (provider, requests, samples):
        events = await voice_events(VoicePipeline(workflow=workflow, config=VoicePipelineConfig(
            model_provider=provider, tracing_disabled=True)), AudioInput(source))
    np.testing.assert_array_equal(requests[0][1]['samples'], source)
    assert workflow.inputs == ['The green suitcase']
    synthesized = synthesis_requests(requests)
    assert ''.join(body['input'] for body in synthesized) == 'Spoken reply: The green suitcase.'
    np.testing.assert_array_equal(speech_samples(events), repeated_samples(samples, len(synthesized)))
    assert voice_order(events) == ['turn_started', 'audio', 'turn_ended', 'session_ended']


@pytest.mark.asyncio
async def test_f19_t02():
    for turns in (['First destination', 'Second destination'], []):
        workflow = SpeechWorkflow()
        async with speech_provider(audio_for_text=text_samples) as (provider, requests, samples):
            async with transcription_socket(turns) as (url, peer):
                async with AsyncOpenAI(api_key='local-service-key', websocket_base_url=url) as client:
                    stt = OpenAIVoiceModelProvider(openai_client=client).get_stt_model(None)
                    audio = StreamedAudioInput()
                    chunks = [np.array([index + 307, -811], dtype=np.int16) for index in range(len(turns))]
                    for chunk in chunks:
                        await audio.add_audio(chunk)
                    await audio.add_audio(None)
                    events = await voice_events(VoicePipeline(workflow=workflow, stt_model=stt,
                        config=VoicePipelineConfig(model_provider=provider, tracing_disabled=True)), audio)
                sent = [request for request in peer.requests if request['type'] == 'input_audio_buffer.append']
                import base64
                assert b''.join(base64.b64decode(item['audio']) for item in sent) == b''.join(
                    chunk.tobytes() for chunk in chunks)
        assert workflow.inputs == turns
        expected_text = ''.join('Spoken reply: ' + turn + '.' for turn in turns)
        assert ''.join(body['input'] for body in synthesis_requests(requests)) == expected_text
        assert voice_order(events) == ['turn_started', 'audio', 'turn_ended'] * len(turns) + ['session_ended']
        if turns:
            np.testing.assert_array_equal(speech_samples(events), text_samples(expected_text))


@pytest.mark.asyncio
async def test_f19_t03():
    context = {'private': 'not-for-model-voice-secret', 'count': 0}
    seen = []

    async def apply(wrapper, arguments):
        seen.append(wrapper.context)
        wrapper.context['count'] += 1
        return 'Application action completed'

    tool = FunctionTool(name='advance', description='Advance application state.',
        params_json_schema={'type': 'object', 'properties': {}, 'additionalProperties': False}, on_invoke_tool=apply)
    target_model = VoiceStreamModel([function_call('advance', {}, 'one')], 'First answer.',
                                      [function_call('advance', {}, 'two')], 'Second answer.')
    callback_contexts = []

    def instructions(wrapper, agent):
        callback_contexts.append(wrapper.context)
        return 'Speak clearly.'

    target = Agent(name='Continuing speaker', model=target_model, tools=[tool], instructions=instructions)
    transfer = handoff(target)
    initial_model = VoiceStreamModel([function_call(transfer.tool_name, {}, 'transfer')])
    initial = Agent(name='Initial speaker', model=initial_model, handoffs=[transfer])

    class Callbacks:
        def __init__(self):
            self.inputs = []
        def on_run(self, workflow, transcription):
            self.inputs.append(transcription)

    callbacks = Callbacks()
    workflow = SingleAgentVoiceWorkflow(initial, callbacks, context=context)
    with tool_trace_destination():
        assert ''.join(await consume(workflow.run('Start the route'))) == 'First answer.'
        assert ''.join(await consume(workflow.run('Continue the route'))) == 'Second answer.'
    assert callbacks.inputs == ['Start the route', 'Continue the route']
    assert len(initial_model.requests) == 1
    assert len(target_model.requests) == 4
    assert seen == [context, context] and all(item is context for item in seen)
    assert context['count'] == 2
    assert callback_contexts and all(item is context for item in callback_contexts)
    history = history_contents(target_model.requests[2]['input'])
    assert 'Start the route' in history and 'First answer.' in history and 'Continue the route' in history
    assert context['private'] not in json.dumps([item['input'] for item in initial_model.requests + target_model.requests]
            + initial_model.instructions_seen + target_model.instructions_seen)


@pytest.mark.asyncio
async def test_f19_t04():
    async with speech_provider() as (provider, requests, samples):
        for stt_name, tts_name in ((None, None), ('whisper-1', 'tts-1')):
            offset = len(requests)
            await voice_events(VoicePipeline(workflow=SpeechWorkflow(), stt_model=stt_name, tts_model=tts_name,
                config=VoicePipelineConfig(model_provider=provider, tracing_disabled=True,
                    stt_settings=STTModelSettings(language='fr', prompt='Travel recording'))),
                AudioInput(np.array([71, -83], dtype=np.int16)))
            current = requests[offset:]
            transcription = [body for path, body in current if path == '/v1/audio/transcriptions']
            synthesis = synthesis_requests(current)
            assert len(transcription) == 1 and synthesis
            assert transcription[0]['model'] == ('gpt-transcribe' if stt_name is None else stt_name).encode()
            assert transcription[0]['languages[]' if stt_name is None else 'language'] == b'fr'
            assert transcription[0]['prompt'] == b'Travel recording'
            assert all(body['model'] == ('gpt-4o-mini-tts' if tts_name is None else tts_name)
                       for body in synthesis)
    application = ApplicationVoiceProvider()
    events = await voice_events(VoicePipeline(workflow=SpeechWorkflow(), stt_model='chosen-recognizer',
        tts_model='chosen-speaker', config=VoicePipelineConfig(model_provider=application, tracing_disabled=True)),
        AudioInput(np.array([61], dtype=np.int16)))
    assert set(application.selections) == {('stt', 'chosen-recognizer'), ('tts', 'chosen-speaker')}
    assert ''.join(application.tts.inputs) == 'Spoken reply: Application transcription.'
    np.testing.assert_array_equal(speech_samples(events), repeated_samples([1001, -7002], len(application.tts.inputs)))
    for model in ('gpt-transcribe', 'gpt-live-transcribe'):
        for languages in (None, ['fr', 'de']):
            async with transcription_socket([]) as (url, peer):
                async with AsyncOpenAI(api_key='local-service-key', websocket_base_url=url) as client:
                    provider = OpenAIVoiceModelProvider(openai_client=client)
                    audio = StreamedAudioInput()
                    await audio.add_audio(None)
                    await voice_events(VoicePipeline(workflow=SpeechWorkflow(), stt_model=model,
                        tts_model=ApplicationTTS(), config=VoicePipelineConfig(model_provider=provider,
                        tracing_disabled=True, stt_settings=STTModelSettings(language='es', languages=languages,
                            keywords=['itinerary', 'terminal'], prompt='Route notes'))), audio)
                update = next(item for item in peer.requests if item['type'] == 'session.update')
                settings = update['session']['audio']['input']['transcription']
                assert settings['model'] == model
                assert settings['languages'] == (languages if languages is not None else ['es'])
                assert 'language' not in settings
                assert settings['keywords'] == ['itinerary', 'terminal']
                assert settings['prompt'] == 'Route notes'


@pytest.mark.asyncio
async def test_f19_t05():
    voices = [None, 'alloy', 'ash', 'ballad', 'coral', 'echo', 'fable', 'onyx', 'nova',
              'sage', 'shimmer', 'verse', 'marin', 'cedar', {'id': 'existing-application-voice'}]
    async with speech_provider() as (provider, requests, samples):
        for voice in voices:
            offset = len(requests)
            events = await voice_events(VoicePipeline(workflow=SpeechWorkflow(),
                stt_model=ApplicationSTT(), config=VoicePipelineConfig(model_provider=provider,
                tracing_disabled=True, tts_settings=TTSModelSettings(voice=voice))),
                AudioInput(np.array([901], dtype=np.int16)))
            synthesized = synthesis_requests(requests[offset:])
            assert synthesized and all(body['voice'] == ('ash' if voice is None else voice)
                                       for body in synthesized)
            np.testing.assert_array_equal(speech_samples(events), repeated_samples(samples, len(synthesized)))


@pytest.mark.asyncio
async def test_f19_t06():
    for spelling in (None, 'int16', np.dtype('i2'), 'float32', 'f4'):
        settings = TTSModelSettings() if spelling is None else TTSModelSettings(dtype=spelling)
        async with speech_provider() as (provider, requests, samples):
            events = await voice_events(VoicePipeline(workflow=SpeechWorkflow(), stt_model=ApplicationSTT(),
                config=VoicePipelineConfig(model_provider=provider, tracing_disabled=True, tts_settings=settings)),
                AudioInput(np.array([32], dtype=np.int16)))
        samples = repeated_samples(samples, len(synthesis_requests(requests)))
        actual = speech_samples(events)
        expected_dtype = np.dtype(np.int16 if spelling is None else spelling)
        assert actual.dtype == expected_dtype and actual.dtype.isnative
        if actual.dtype == np.dtype('int16'):
            np.testing.assert_array_equal(actual, samples)
        else:
            # Compare against a permissible scale interval, not the reference divisor.
            low = np.minimum(samples / 32768.0, samples / 32767.0) - np.finfo(np.float32).eps
            high = np.maximum(samples / 32768.0, samples / 32767.0) + np.finfo(np.float32).eps
            assert actual.shape == samples.shape
            assert np.all(actual >= low) and np.all(actual <= high)
            nonzero = samples != 0
            magnitudes = np.abs(actual[nonzero].astype(np.float64))
            pcm_magnitudes = np.abs(samples[nonzero].astype(np.float64))
            epsilon = np.finfo(np.float32).eps
            minimum_scale = max(32767.0, np.max(pcm_magnitudes / (magnitudes + epsilon)))
            maximum_scale = min(32768.0, np.min(pcm_magnitudes / (magnitudes - epsilon)))
            assert minimum_scale <= maximum_scale
    for spelling in ('int32', 'float64', np.dtype('i2').newbyteorder('S')):
        with pytest.raises(UserError):
            await voice_events(VoicePipeline(workflow=SpeechWorkflow(), stt_model=ApplicationSTT(),
                tts_model=ApplicationTTS(), config=VoicePipelineConfig(tracing_disabled=True,
                    tts_settings=TTSModelSettings(dtype=spelling))), AudioInput(np.array([32], dtype=np.int16)))


@pytest.mark.asyncio
async def test_f19_t07():
    session = TurnSession(['A successful turn'])
    audio = StreamedAudioInput()
    await audio.add_audio(None)
    tts = ApplicationTTS()
    events = await voice_events(VoicePipeline(workflow=SpeechWorkflow(), stt_model=ApplicationSTT(session),
        tts_model=tts, config=VoicePipelineConfig(tracing_disabled=True)), audio)
    assert session.closed
    assert voice_order(events) == ['turn_started', 'audio', 'turn_ended', 'session_ended']
    np.testing.assert_array_equal(speech_samples(events), repeated_samples([1001, -7002], len(tts.inputs)))
    for stage in ('transcription', 'workflow', 'synthesis', 'cleanup', 'turn-and-cleanup'):
        primary, cleanup = ValueError('Application turn failure'), RuntimeError('Application close failure')
        session = TurnSession(['Recognized turn'],
            error=primary if stage in ('transcription', 'turn-and-cleanup') else None,
            close_error=cleanup if stage in ('cleanup', 'turn-and-cleanup') else None)
        workflow = SpeechWorkflow(error=primary if stage == 'workflow' else None)
        delivered = asyncio.Event()
        tts = ApplicationTTS(error=primary if stage == 'synthesis' else None, delivery_gate=delivered)

        def on_event(event):
            if event.type == 'voice_stream_event_audio':
                delivered.set()
        audio = StreamedAudioInput()
        await audio.add_audio(None)
        observed = Observation()
        expected = cleanup if stage == 'cleanup' else primary
        with pytest.raises(type(expected)) as raised:
            await voice_events(VoicePipeline(workflow=workflow, stt_model=ApplicationSTT(session),
                tts_model=tts, config=VoicePipelineConfig(tracing_disabled=True,
                    tts_settings=TTSModelSettings(buffer_size=1))), audio, observation=observed, on_event=on_event)
        assert raised.value is expected
        assert session.closed
        if stage == 'synthesis':
            np.testing.assert_array_equal(speech_samples(observed.items), [1001, -7002])
    # Complete recordings use a separate public input mode and producer path.
    for stage in ('transcription', 'workflow', 'synthesis'):
        error = LookupError('Complete input stage failed')
        with pytest.raises(LookupError) as raised:
            await voice_events(VoicePipeline(
                workflow=SpeechWorkflow(error=error if stage == 'workflow' else None),
                stt_model=ApplicationSTT(error=error if stage == 'transcription' else None),
                tts_model=ApplicationTTS(error=error if stage == 'synthesis' else None),
                config=VoicePipelineConfig(tracing_disabled=True)),
                AudioInput(np.array([73], dtype=np.int16)))
        assert raised.value is error


@pytest.mark.asyncio
async def test_f19_t08():
    for options, text_enabled, audio_enabled, disabled in (
        ({}, True, True, False),
        ({'trace_include_sensitive_data': False}, False, True, False),
        ({'trace_include_sensitive_audio_data': False}, True, False, False),
        ({'trace_include_sensitive_data': False, 'trace_include_sensitive_audio_data': False}, False, False, False),
        ({'tracing_disabled': True}, False, False, True),
    ):
        with tool_trace_destination() as collector:
            async with speech_provider(transcript='Private travel phrase') as (provider, requests, samples):
                events = await voice_events(VoicePipeline(workflow=SpeechWorkflow(),
                    config=VoicePipelineConfig(model_provider=provider,
                        stt_settings=STTModelSettings(prompt='Private recording context'),
                        tts_settings=TTSModelSettings(instructions='Private speaking direction'), **options)),
                    AudioInput(np.array([4101, -9912], dtype=np.int16)))
                synthesized = synthesis_requests(requests)
                assert ''.join(body['input'] for body in synthesized) == 'Spoken reply: Private travel phrase.'
                np.testing.assert_array_equal(speech_samples(events), repeated_samples(samples, len(synthesized)))
        spans = [item['span_data'] for item in collector.spans]
        if disabled:
            assert spans == []
            continue
        transcription = [span for span in spans if span['type'] == 'transcription']
        synthesis = [span for span in spans if span['type'] == 'speech']
        assert len(transcription) == 1
        assert len(synthesis) == len(synthesized) and synthesis
        assert transcription[0]['output'] in (['Private travel phrase'] if text_enabled else [None, ''])
        from collections import Counter
        assert Counter(span['input'] for span in synthesis) == Counter(
            body['input'] if text_enabled else '' for body in synthesized)
        assert transcription[0]['model_config']['prompt'] == ('Private recording context' if text_enabled else None)
        assert all(span['model_config']['instructions'] == ('Private speaking direction' if text_enabled else None)
                   for span in synthesis)
        groups = [span for span in spans if span['type'] == 'speech_group']
        if not text_enabled:
            assert all(span['input'] in (None, '') for span in groups)
        import base64
        assert transcription[0]['input']['data'] == (base64.b64encode(np.array([4101, -9912], dtype=np.int16).tobytes()).decode() if audio_enabled else '')
        assert all(span['output']['data'] == (base64.b64encode(samples.tobytes()).decode() if audio_enabled else '')
                   for span in synthesis)
