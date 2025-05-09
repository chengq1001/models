# Copyright 2024 Huawei Technologies Co., Ltd
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ============================================================================
"""llama2 predict example."""
import argparse
import os

from mindspore.communication import get_rank

from mindformers import MindFormerConfig, build_context, logger
from mindformers.experimental.infer.core.utils import generate_state_dict
from mindformers.experimental.infer.models.llama import ParallelLlamaForCausalLM
from mindformers.experimental.parallel_core.pynative.utils import save_strategy_file
from mindformers.models.llama import LlamaConfig, LlamaTokenizer
from mindformers.tools.utils import get_output_root_path
from mindformers.trainer.utils import load_ckpt


def main(config_path, load_checkpoint):
    # multi batch inputs
    inputs = ["I love Beijing, because",
              "LLaMA is a",
              "Huawei is a company that"]
    batch_size = len(inputs)

    # init config with yaml
    config = MindFormerConfig(config_path)
    config.use_parallel = True
    device_num = os.getenv('MS_WORKER_NUM')
    logger.info(f"Use device number: {device_num}, it will override config.model_parallel.")
    config.parallel_config.model_parallel = int(device_num) if device_num else 1
    config.parallel_config.data_parallel = 1
    config.parallel_config.pipeline_stage = 1
    config.load_checkpoint = load_checkpoint

    # init context
    build_context(config)

    # build model config
    config.model.model_config.parallel_config = config.parallel_config
    config.model.model_config.batch_size = batch_size
    model_config = LlamaConfig(**config.model.model_config)
    model_config.checkpoint_name_or_path = None
    model_name = config.trainer.model_name

    # build tokenizer
    tokenizer = LlamaTokenizer.from_pretrained(model_name)

    # build model
    network = ParallelLlamaForCausalLM(model_config)

    # get strategy file
    if config.only_save_strategy:
        strategy_ckpt_save_dir = os.path.join(get_output_root_path(), "strategy")
        os.makedirs(strategy_ckpt_save_dir, exist_ok=True)
        strategy_file_path = os.path.join(strategy_ckpt_save_dir, "ckpt_strategy.ckpt")
        shard_state_dict = generate_state_dict(network)
        if get_rank() == 0:
            save_strategy_file(shard_state_dict, strategy_file_path)
        logger.info(f"Strategy file has been saved in {strategy_file_path}.")
        return

    # load checkpoint
    load_ckpt(config, network)

    # generate
    inputs_ids = tokenizer(inputs, max_length=model_config.seq_length, padding="max_length")["input_ids"]
    outputs = network.generate(inputs_ids,
                               max_length=model_config.max_decode_length,
                               do_sample=model_config.do_sample,
                               top_k=model_config.top_k,
                               top_p=model_config.top_p)
    for output in outputs:
        logger.info("tokenizer.decode(output) is : %s", tokenizer.decode(output))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--config_path', default='predict_llama2_7b.yaml', type=str,
                        help='model config file path.')
    parser.add_argument('--load_checkpoint', type=str,
                        help='load model checkpoint path or directory.')

    args = parser.parse_args()
    main(args.config_path, args.load_checkpoint)
