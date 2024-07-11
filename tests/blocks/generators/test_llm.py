# Standard
from typing import Dict, List
import copy
import os
import time

# Third Party
import pytest

# Local
from fms_dgt.base.registry import get_block
from fms_dgt.blocks.generators.llm import CachingLM, LMGenerator

# hf cache

BASE_PATH = os.path.dirname(os.path.realpath(__file__))
os.environ["HF_HOME"] = os.path.join(BASE_PATH, ".cache", "huggingface", "transformers")
os.environ["HF_DATASETS_CACHE"] = os.path.join(
    BASE_PATH, ".cache", "huggingface", "datasets"
)

#

GREEDY_CFG = {
    "decoding_method": "greedy",
    "temperature": 1.0,
    "max_new_tokens": 5,
    "min_new_tokens": 1,
}
GREEDY_GENAI_CFG = {
    "type": "genai",
    "model_id_or_path": "ibm/granite-8b-code-instruct",
    **GREEDY_CFG,
}
GREEDY_VLLM_CFG = {
    "type": "vllm",
    "model_id_or_path": "ibm-granite/granite-8b-code-instruct",
    **GREEDY_CFG,
}
GREEDY_OPENAI_CFG = {
    "type": "openai-chat",
    "model_id_or_path": "gpt-3.5-turbo",
    **GREEDY_CFG,
}
PROMPTS = [f"Question: x = {i} + 1\nAnswer: x =" for i in range(25)]


class TestLlmGenerators:
    @pytest.mark.parametrize(
        "model_cfg", [GREEDY_GENAI_CFG, GREEDY_OPENAI_CFG]
    )  # GREEDY_VLLM_CFG]
    def test_generate_batch(self, model_cfg):
        model_cfg = dict(model_cfg)
        model_type = model_cfg.pop("type")
        lm: LMGenerator = get_block(model_type)(name=f"test_{model_type}", **model_cfg)

        inputs: List[Dict] = []
        for prompt in PROMPTS:
            inp = {"prompt": prompt}
            inputs.append(inp)

        inputs_copy = copy.deepcopy(inputs)

        lm.generate(inputs, arg_fields=["prompt"], result_field="output")

        for i, inp in enumerate(inputs):
            assert (
                inp["prompt"] == inputs_copy[i]["prompt"]
            ), f"Input list has been rearranged at index {i}"
            assert isinstance(inp["output"], str)

    @pytest.mark.parametrize("model_cfg", [GREEDY_GENAI_CFG])  # , GREEDY_VLLM_CFG])
    def test_loglikelihood_batch(self, model_cfg):
        model_cfg = dict(model_cfg)
        model_type = model_cfg.pop("type")
        lm: LMGenerator = get_block(model_type)(name=f"test_{model_type}", **model_cfg)

        inputs: List[Dict] = []
        for prompt in PROMPTS:
            inp = {"prompt1": prompt, "prompt2": prompt}
            inputs.append(inp)

        inputs_copy = copy.deepcopy(inputs)

        lm.generate(
            inputs,
            arg_fields=["prompt1", "prompt2"],
            result_field="output",
            method="loglikelihood",
        )

        for i, inp in enumerate(inputs):
            assert (
                inp["prompt1"] == inputs_copy[i]["prompt1"]
            ), f"Input list has been rearranged at index {i}"
            assert isinstance(inp["output"], float)

    # def test_loglikelihood_batch_alignment(self):
    #     vllm_config, genai_config = dict(GREEDY_VLLM_CFG), dict(GREEDY_GENAI_CFG)
    #     vllm_config["model_id_or_path"] = "ibm-granite/granite-8b-code-instruct"
    #     genai_config["model_id_or_path"] = "ibm/granite-8b-code-instruct"

    #     vllm: LMGeneratorBlock = get_block(vllm_config["type"])(
    #         name=f"test_{vllm_config['type']}", config=vllm_config
    #     )
    #     genai: LMGeneratorBlock = get_block(genai_config["type"])(
    #         name=f"test_{genai_config['type']}", config=genai_config
    #     )

    #     inputs: List[Instance] = []
    #     for prompt in PROMPTS[:1]:
    #         args = [prompt, prompt]
    #         inputs.append(Instance(args))

    #     inputs_vllm = copy.deepcopy(inputs)
    #     inputs_genai = copy.deepcopy(inputs)

    #     vllm.loglikelihood_batch(inputs_vllm)
    #     genai.loglikelihood_batch(inputs_genai)

    #     for i, inp in enumerate(inputs):
    #         assert (
    #             inp.args == inputs_vllm[i].args == inputs_genai[i].args
    #         ), f"Input list has been rearranged at index {i}"

    def test_lm_caching(self):
        cache_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "tmp_cache.db"
        )
        if os.path.exists(cache_path):
            os.remove(cache_path)

        model_cfg = dict(GREEDY_GENAI_CFG)
        model_type = model_cfg.pop("type")
        lm: LMGenerator = get_block(model_type)(name=f"test_{model_type}", **model_cfg)

        non_cache_inputs: List[Dict] = []
        for prompt in PROMPTS:
            inp = {"prompt": prompt}
            non_cache_inputs.append(inp)

        pre_cache_inputs = copy.deepcopy(non_cache_inputs)
        post_cache_inputs = copy.deepcopy(non_cache_inputs)

        non_cache_time = time.time()
        lm.generate(non_cache_inputs, arg_fields=["prompt"], result_field="output")
        non_cache_time = time.time() - non_cache_time

        cache_lm = CachingLM(
            lm,
            cache_path,
        )

        pre_cache_time = time.time()
        cache_lm.generate(
            pre_cache_inputs, arg_fields=["prompt"], result_field="output"
        )
        pre_cache_time = time.time() - pre_cache_time

        post_cache_time = time.time()
        cache_lm.generate(
            post_cache_inputs, arg_fields=["prompt"], result_field="output"
        )
        post_cache_time = time.time() - post_cache_time

        os.remove(cache_path)

        assert (
            post_cache_time < pre_cache_time and post_cache_time < non_cache_time
        ), f"Caching led to increased execution time {(post_cache_time, pre_cache_time, non_cache_time)}"

        for i, (non, pre, post) in enumerate(
            zip(non_cache_inputs, pre_cache_inputs, post_cache_inputs)
        ):
            assert (
                non["prompt"] == pre["prompt"] == post["prompt"]
            ), f"Input list has been rearranged at index {i}: {(non['prompt'], pre['prompt'], post['prompt'])}"
            assert (
                non["output"] == pre["output"] == post["output"]
            ), f"Different results detected at index {i}: {(non['output'], pre['output'], post['output'])}"
