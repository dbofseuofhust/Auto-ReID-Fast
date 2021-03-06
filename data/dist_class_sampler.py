
import torch
import math
from torch.utils.data.sampler import Sampler
import utils.distributed.misc as misc


class DistributedSampler(Sampler):
    """Sampler that restricts data loading to a subset of the dataset.

    It is especially useful in conjunction with
    :class:`torch.nn.parallel.DistributedDataParallel`. In such case, each
    process can pass a DistributedSampler instance as a DataLoader sampler,
    and load a subset of the original dataset that is exclusive to it.

    .. note::
        Dataset is assumed to be of constant size.

    Arguments:
        dataset: Dataset used for sampling.
        world_size (optional): Number of processes participating in
            distributed training.
        rank (optional): Rank of the current process within world_size.
    """

    def __init__(self, dataset, dataset_len, world_size=None, rank=None, round_up=True, shuffle = True, pair_num = 4):
        if world_size is None:
            world_size = misc.get_world_size()
        if rank is None:
            rank = misc.get_rank()
        self.dataset = dataset
        self.dataset_len = dataset_len
        self.world_size = world_size
        self.rank = rank
        self.round_up = round_up
        self.epoch = 0
        self.shuffle = shuffle
        self.pair_num = pair_num
        
        self.num_samples = int(math.ceil(self.dataset_len * 1.0 / self.world_size))
        if self.round_up:
            self.total_size = self.num_samples * self.world_size
        else:
            self.total_size = self.dataset_len

    def __iter__(self):
        # deterministically shuffle based on epoch
        g = torch.Generator()
        g.manual_seed(self.epoch)
        if self.shuffle:
            indices = list(torch.randperm(self.dataset_len, generator=g))
            # re-range index
            target_label = 0
            size = len(indices)
            for i in range(size):
                if i % self.pair_num == 0:
                    target_label = self.dataset.imgs[indices[i]][1]
                    continue
                for j in range(i + 1, size):
                    if self.dataset.imgs[indices[j]][1] == target_label:
                        indices[i], indices[j] = indices[j], indices[i]
                        break
                    if j == (size - 1): # not multiple of pair_num
                        indices[i] = indices[i-1]
        else:
            indices = list(range(len(self.dataset)))

        # add extra samples to make it evenly divisible
        if self.round_up:
            indices += indices[:(self.total_size - len(indices))]
        assert len(indices) == self.total_size

        # subsample
        offset = self.num_samples * self.rank
        indices = indices[offset:offset + self.num_samples]
        if self.round_up or (not self.round_up and self.rank < self.world_size-1):
            assert len(indices) == self.num_samples

        return iter(indices)

    def __len__(self):
        return self.num_samples

    def set_epoch(self, epoch):
        self.epoch = epoch