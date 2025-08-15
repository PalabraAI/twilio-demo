import copy
import os

host = os.getenv('HOST')
client_settings = {
    'input_stream': {
        'content_type': 'audio',
        'source': {
            'type': 'ws',
            'format': 'pcm_s16le',
            'sample_rate': 24_000,
            'channels': 1,
        },
    },
    'output_stream': {
        'content_type': 'audio',
        'target': {'type': 'ws', 'format': 'pcm_s16le', 'sample_rate': 24_000, 'channels': 1},
    },
    'pipeline': {
        'preprocessing': {},
        'transcription': {
            'source_language': 'en',
            'detectable_languages': ['ru', 'en'],
            'asr_model': 'auto',
            'segment_confirmation_silence_threshold': 0.7,
            'sentence_splitter': {
                'enabled': True,
            },
            'verification': {
                'auto_transcription_correction': False,
                'transcription_correction_style': None,
            },
        },
        'translations': [
            {
                'target_language': 'ru',
                'translate_partial_transcriptions': False,
            },
        ],
    },
    "translation_queue_configs": {
        "global": {
            "desired_queue_level_ms": 10000,
            "max_queue_level_ms": 24000,
            "auto_tempo": True,
            "min_tempo": 1.0,
            "max_tempo": 1.2,
        },
    },
}
operator_settings = copy.deepcopy(client_settings)
operator_settings['pipeline']['translations'][0]['target_language'] = 'en'
operator_settings['pipeline']['transcription']['source_language'] = 'ru'
role_settings = {
    'client': client_settings,
    'operator': operator_settings,
}
