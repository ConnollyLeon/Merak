
def load_config(model_name):
    if model_name == "gpt2":
        config = {
            'activation_function': 'gelu', 
            'architectures': ['GPT2LMHeadModel'], 
            'attn_pdrop': 0.1, 
            'bos_token_id': 50256, 
            'embd_pdrop': 0.1, 
            'eos_token_id': 50256, 
            'initializer_range': 0.02, 
            'layer_norm_epsilon': 1e-05, 
            'model_type': 'gpt2', 
            "n_ctx": 1024,
            'n_embd': 768, 
            'n_head': 12, 
            'n_layer': 12, 
            'n_positions': 1024, 
            'resid_pdrop': 0.1, 
            'summary_activation': None, 
            'summary_first_dropout': 0.1, 
            'summary_proj_to_labels': True, 
            'summary_type': 'cls_index', 
            'summary_use_proj': True, 
            'task_specific_params': {'text-generation': {'do_sample': True, 'max_length': 50}}, 
            'vocab_size': 50257,
            'return_dict': False,
            'reorder_and_upcast_attn': True,
            'use_cache': False
            }
    elif model_name == "t5-base":
        config = {
            'architectures': ['T5WithLMHeadModel'], 
            'd_ff': 3072, 
            'd_kv': 64, 
            'd_model': 512, 
            'decoder_start_token_id': 0, 
            'dropout_rate': 0.1, 
            'eos_token_id': 1, 
            'initializer_factor': 1.0, 
            'is_encoder_decoder': True, 
            'layer_norm_epsilon': 1e-06, 
            'model_type': 't5', 
            'n_positions': 512, 
            'num_heads': 16, 
            'num_layers': 8, 
            'output_past': True, 
            'pad_token_id': 0, 
            'relative_attention_num_buckets': 32, 
            'task_specific_params': {'summarization': {'early_stopping': True, 'length_penalty': 2.0, 'max_length': 200, 'min_length': 30, 'no_repeat_ngram_size': 3, 'num_beams': 4, 'prefix': 'summarize: '}, 
            'translation_en_to_de': {'early_stopping': True, 'max_length': 300, 'num_beams': 4, 'prefix': 'translate English to German: '}, 
            'translation_en_to_fr': {'early_stopping': True, 'max_length': 300, 'num_beams': 4, 
            'prefix': 'translate English to French: '}, 
            'translation_en_to_ro': {'early_stopping': True, 'max_length': 300, 
            'num_beams': 4, 
            'prefix': 'translate English to Romanian: '}}, 
            'vocab_size': 32128,
            'use_cache': False,
            'return_dict': False,
            }
    elif model_name == "bert-large-uncased":
        config = {
            'architectures': ['BertForMaskedLM'], 
            'attention_probs_dropout_prob': 0.1, 
            'gradient_checkpointing': False, 
            'hidden_act': 'gelu', 
            'hidden_dropout_prob': 0.1, 
            'hidden_size': 1024, 
            'initializer_range': 0.02, 
            'intermediate_size': 4096, 
            'layer_norm_eps': 1e-12, 
            'max_position_embeddings': 512, 
            'model_type': 'bert', 
            'num_attention_heads': 16, 
            'num_hidden_layers': 24, 
            'pad_token_id': 0, 
            'position_embedding_type': 'absolute', 
            'type_vocab_size': 2, 
            'use_cache': False, 
            'vocab_size': 30522,
            } 
    else:
        raise ValueError(f"No {model_name} config")

    return config
