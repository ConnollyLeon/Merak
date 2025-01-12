# coding=utf-8
# Copyright (c) 2022, HPDL group, PDL lab, NUDT.  All rights reserved.
#
# Maintainer: TXacs (txacs1993@gmail.com)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Parts of the code here are adapted from https://github.com/NVIDIA/Megatron-LM/blob/v2.6/megatron/checkpointing.py

import random
import sys
import os
import numpy as np
from numpy.lib import utils

import torch
from .. import mpu, print_rank_0
from ..runtime.checkpointing import get_cuda_rng_tracker
import torch.distributed as dist

_CHECKPOINT_VERSION = None

def set_checkpoint_version(value):
    global _CHECKPOINT_VERSION
    if _CHECKPOINT_VERSION is not None:
        assert _CHECKPOINT_VERSION == value, \
            "checkpoint versions do not match"
    _CHECKPOINT_VERSION = value

def get_checkpoint_version():
    global _CHECKPOINT_VERSION
    return _CHECKPOINT_VERSION

def get_checkpoint_name(checkpoints_path, iteration,
                        release=False, complete=False):
    """A unified checkpoint name."""
    if release:
        directory = 'release'
    else:
        directory = 'iter_{:07d}'.format(iteration)
    # Use both the tensor and pipeline MP rank.
    if mpu.get_pipe_parallel_world_size() == 1:
        if complete:
            return os.path.join(checkpoints_path,
                            'iter_{:07d}_mp_rank_{:02d}'.format(
                                iteration,
                                mpu.get_tensor_model_parallel_rank()),
                            'complete_model_optim.pt')
        return os.path.join(checkpoints_path, directory,
                            'mp_rank_{:02d}'.format(
                                mpu.get_tensor_model_parallel_rank()),
                            'model_optim_rng.pt')
    if complete:
        return os.path.join(checkpoints_path, directory,
                        'iter_{:07d}_mp_rank_{:02d}_pp_rank_{:03d}'.format(
                            iteration,
                            mpu.get_model_parallel_rank(),
                            mpu.get_pipe_parallel_rank()),
                        'complete_model_optim.pt')
    return os.path.join(checkpoints_path, directory,
                        'mp_rank_{:02d}_pp_rank_{:03d}'.format(
                            mpu.get_model_parallel_rank(),
                            mpu.get_pipe_parallel_rank()),
                        'model_optim_rng.pt')

def ensure_directory_exists(filename):
    """Build filename's path if it does not already exists."""
    dirname = os.path.dirname(filename)
    if not os.path.exists(dirname):
        os.makedirs(dirname)

def check_checkpoint_args(checkpoint_args, args):
    """Ensure fixed arguments for a model are the same for the input
    arguments and the one retrieved from checkpoint."""

    def _compare(arg_name, old_arg_name=None):
        if old_arg_name is not None:
            checkpoint_value = getattr(checkpoint_args, old_arg_name)
        else:
            checkpoint_value = getattr(checkpoint_args, arg_name)
        args_value = getattr(args, arg_name)
        error_message = '{} value from checkpoint ({}) is not equal to the ' \
                        'input argument value ({}).'.format(
                            arg_name, checkpoint_value, args_value)
        assert checkpoint_value == args_value, error_message

def get_checkpoint_tracker_filename(checkpoints_path):
    """Tracker file rescords the latest chckpoint during
    training to restart from."""
    return os.path.join(checkpoints_path, 'latest_checkpointed_iteration.txt')


def read_metadata(tracker_filename):
    # Read the tracker file and either set the iteration or
    # mark it as a release checkpoint.
    iteration = 0
    release = False
    with open(tracker_filename, 'r') as f:
        metastring = f.read().strip()
        try:
            iteration = int(metastring)
        except ValueError:
            release = metastring == 'release'
            if not release:
                print_rank_0('ERROR: Invalid metadata file {}. Exiting'.format(
                    tracker_filename))
                sys.exit()
    assert iteration > 0 or release, 'error parsing metadata file {}'.format(
        tracker_filename)

    # Get the max iteration retrieved across the ranks.
    iters_cuda = torch.cuda.LongTensor([iteration])
    torch.distributed.all_reduce(iters_cuda, op=torch.distributed.ReduceOp.MAX)
    max_iter = iters_cuda[0].item()

    # We should now have all the same iteration.
    # If not, print a warning and chose the maximum
    # iteration across all ranks.
    if iteration != max_iter:
        print('WARNING: on rank {} found iteration {} in the '
              'metadata while max iteration across the ranks '
              'is {}, replacing it with max iteration.'.format(
                  mpu.get_pipe_parallel_rank(), iteration, max_iter), flush=True)
    return max_iter, release

def save_checkpoint(iteration, model, optimizer, lr_scheduler, args, epoch):
    """Save a model checkpoint."""

    # Only rank zero of the data parallel writes to the disk.
    model = unwrap_model(model)

    print_rank_0('saving checkpoint at iteration {:7d} to {}'.format(
        iteration, args.output_dir+'/ckpt'))

    if not torch.distributed.is_initialized() or mpu.get_data_parallel_rank() == 0:

        # Arguments, iteration, and model.
        state_dict = {}
        state_dict['args'] = args
        state_dict['checkpoint_version'] = 3.0
        state_dict['iteration'] = iteration
        state_dict['model'] = model.state_dict()
        state_dict['epoch'] = epoch

        # Optimizer stuff.
        if not args.no_save_optim:
            if optimizer is not None:
                state_dict['optimizer'] = optimizer.state_dict()
            if lr_scheduler is not None:
                state_dict['lr_scheduler'] = lr_scheduler.state_dict()

        # RNG states.
        if not args.no_save_rng:
            state_dict['random_rng_state'] = random.getstate()
            state_dict['np_rng_state'] = np.random.get_state()
            state_dict['torch_rng_state'] = torch.get_rng_state()
            state_dict['cuda_rng_state'] = torch.cuda.get_rng_state()
            state_dict['rng_tracker_states'] \
                = get_cuda_rng_tracker().get_states()

        # save a complete model
        # comp_model = {}
        # print(state_dict['model'])
        # comp_model['model'] = dist.reduce(state_dict['model'], dst=0)
        # check_name = get_checkpoint_name(args.save, iteration, complete=True)
        # ensure_directory_exists(check_name)
        # torch.save(comp_model, check_name, _use_new_zipfile_serialization=False)

        # Save.
        checkpoint_name = get_checkpoint_name(args.output_dir+'/ckpt', iteration)
        ensure_directory_exists(checkpoint_name)
        torch.save(state_dict, checkpoint_name, _use_new_zipfile_serialization=False)

    # Wait so everyone is done (necessary)
    if torch.distributed.is_initialized():
        torch.distributed.barrier()

    print_rank_0('  successfully saved checkpoint at iteration {:7d} to {}'.format(
        iteration, args.output_dir+'/ckpt'))

    # And update the latest iteration
    if not torch.distributed.is_initialized() or torch.distributed.get_rank() == 0:
        tracker_filename = get_checkpoint_tracker_filename(args.output_dir+'/ckpt')
        with open(tracker_filename, 'w') as f:
            f.write(str(iteration))

    # Wait so everyone is done (not necessary)
    if torch.distributed.is_initialized():
        torch.distributed.barrier()


def load_checkpoint(model, optimizer, lr_scheduler, args, load_arg='load', strict=True):
    """Load a model checkpoint and return the iteration.
    strict (bool): whether to strictly enforce that the keys in
        :attr:`state_dict` of the checkpoint match the names of
        parameters and buffers in model.
    """

    load_dir = args.resume_from_checkpoint #getattr(args, load_arg)
    model = unwrap_model(model)

    # Read the tracker file and set the iteration.
    tracker_filename = get_checkpoint_tracker_filename(load_dir)

    # If no tracker file, return iretation zero.
    if not os.path.isfile(tracker_filename):
        print_rank_0('WARNING: could not find the metadata file {} '.format(
            tracker_filename))
        print_rank_0('    will not load any checkpoints and will start from '
                     'random')
        return 0

    # Otherwise, read the tracker file and either set the iteration or
    # mark it as a release checkpoint.
    iteration, release = read_metadata(tracker_filename)

    # Checkpoint.
    checkpoint_name = get_checkpoint_name(load_dir, iteration, release)
    print_rank_0(f' loading checkpoint from {args.resume_from_checkpoint} at iteration {iteration}')

    # Load the checkpoint.
    print(checkpoint_name)
    try:
        state_dict = torch.load(checkpoint_name, map_location='cpu')
    except BaseException as e:
        print_rank_0('could not load the checkpoint')
        print_rank_0(e)
        sys.exit()

    # set checkpoint version
    set_checkpoint_version(state_dict.get('checkpoint_version', 0))

    # load current epoch
    epoch = state_dict['epoch']

    # Set iteration.
    if args.finetune or release:
        iteration = 0
    else:
        try:
            iteration = state_dict['iteration']
        except KeyError:
            try:  # Backward compatible with older checkpoints
                iteration = state_dict['total_iters']
            except KeyError:
                print_rank_0('A metadata file exists but unable to load '
                             'iteration from checkpoint {}, exiting'.format(
                                 checkpoint_name))
                sys.exit()

    # Check arguments.
    # assert args.consumed_train_samples == 0
    # assert args.consumed_valid_samples == 0
    if 'args' in state_dict:
        checkpoint_args = state_dict['args']
        check_checkpoint_args(checkpoint_args, args)
        args.consumed_train_samples = getattr(checkpoint_args,
                                              'consumed_train_samples', 0)
        # update_num_microbatches(consumed_samples=args.consumed_train_samples)
        args.consumed_valid_samples = getattr(checkpoint_args,
                                              'consumed_valid_samples', 0)
    else:
        print_rank_0('could not find arguments in the checkpoint ...')

    # Model.
    model.load_state_dict(state_dict['model'], strict=strict)

    # Fix up query/key/value matrix ordering if needed
    checkpoint_version = get_checkpoint_version()
    print_rank_0(f' checkpoint version {checkpoint_version}')
    # fix_query_key_value_ordering(model, checkpoint_version)

    # Optimizer.
    if not release and not args.finetune and not args.no_load_optim:
        try:
            if optimizer is not None:
                optimizer.load_state_dict(state_dict['optimizer'])
            if lr_scheduler is not None:
                lr_scheduler.load_state_dict(state_dict['lr_scheduler'])
        except KeyError:
            print_rank_0('Unable to load optimizer from checkpoint {}. '
                         'Specify --no-load-optim or --finetune to prevent '
                         'attempting to load the optimizer state, '
                         'exiting ...'.format(checkpoint_name))
            sys.exit()

    # rng states.
    if not release and not args.finetune and not args.no_load_rng:
        try:
            random.setstate(state_dict['random_rng_state'])
            np.random.set_state(state_dict['np_rng_state'])
            torch.set_rng_state(state_dict['torch_rng_state'])
            torch.cuda.set_rng_state(state_dict['cuda_rng_state'])
            # Check for empty states array
            if not state_dict['rng_tracker_states']:
                raise KeyError
            get_cuda_rng_tracker().set_states(
                state_dict['rng_tracker_states'])
        except KeyError:
            print_rank_0('Unable to load rng state from checkpoint {}. '
                         'Specify --no-load-rng or --finetune to prevent '
                         'attempting to load the rng state, '
                         'exiting ...'.format(checkpoint_name))
            sys.exit()

    # Some utilities want to load a checkpoint without distributed being initialized
    if torch.distributed.is_initialized():
        torch.distributed.barrier()

    print_rank_0(f'  successfully loaded checkpoint from {args.resume_from_checkpoint} '
                 f'at iteration {iteration}')

    return iteration, epoch


def unwrap_model(model):
    return_list = True
    if not isinstance(model, list):
        model = [model]
        return_list = False
    unwrapped_model = []
    for model_module in model:
        unwrapped_model.append(model_module)
    if not return_list:
        return unwrapped_model[0]
    return unwrapped_model