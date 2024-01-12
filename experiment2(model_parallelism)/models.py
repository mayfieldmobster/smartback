from abc import ABC, abstractmethod

import torch
import torch.distributed as dist

import layers

class Model(ABC):
    def __init__(self):
        self.layers: list[layers.Layer] = []
        self.x = ...
        self.dL_dout = ...

    def forward(self, input):
        if dist.get_rank()  == 0:
            for layer in self.layers:
                input = layer(input)
            dist.send(input, dist.get_rank()+1)
        
        elif dist.get_rank() == dist.get_world_size()-1:
            dist.recv(self.x, dist.get_rank()-1)
            for layer in self.layers:
                self.x = layer(self.x)
            return self.x
        
        else:
            dist.recv(self.x, dist.get_rank()-1)
            self.x = self.x
            for layer in self.layers:
                self.x = layer(self.x)
            dist.send(self.x, dist.get_rank()+1)

    def backward(self, dL_dout):
        if dist.get_rank() == dist.get_world_size()-1:
            for layer in self.layers[::-1]:
                dL_dout = layer.backward_p1(dL_dout)
            dist.send(dL_dout, dist.get_rank()-1)
            if layer.multi_stage:
                for layer in self.layers:
                    layer.backward_p2()
            dist.barrier()
        
        elif dist.get_rank() == 0:
            dist.recv(self.dL_dout, dist.get_rank()+1)
            self.dL_dout = self.dL_dout
            for layer in self.layers[::-1]:
                self.dL_dout = layer.backward_p1(self.dL_dout)
                if layer.multi_stage:
                    layer.backward_p2()
            dist.barrier()
        
        else:
            dist.recv(self.dL_dout, dist.get_rank()+1)
            self.dL_dout = self.dL_dout
            for layer in self.layers[::-1]:
                self.dL_dout = layer(self.dL_dout)
            dist.send(dL_dout, self.rank-1)
            if layer.multi_stage:
                for layer in self.layers:
                    layer.backward_p2()
            dist.barrier()
        torch.cuda.synchronize()

    @abstractmethod
    def update(self):
        for layer in self.layers:
            layer.update()
        torch.cuda.synchronize()
        dist.barrier()

    @abstractmethod
    def save(self, path):
        pass

    @abstractmethod
    def load(self, path):
        pass

    def to(self, arg):
        for layer in self.layers:
            layer.to(arg)
        

    
class Transformer(Model):
    def __init__(self, dim_size, num_heads, num_kv_heads, max_seqlen, num_blocks, device):
        self.block_kwargs = {
            "dim_size": dim_size,
            "num_heads": num_heads, 
            "num_kv_heads": num_kv_heads, 
            "max_seqlen": max_seqlen, 
            "device": device
            }
        self.num_blocks = num_blocks
    
    def init_params(self, input_shape):
        self.layers = []
        num_local_blocks = self.num_blocks // dist.get_world_size()
        for _ in range(num_local_blocks):
            layer = layers.TransformerPPBlock(**self.block_kwargs)
            layer.init_params()
            self.layers.append(layer)
        if dist.get_rank() == 0:
            self.layers.insert(0, ...)  # TODO implement embeddings
        
        if dist.get_rank() == dist.get_world_size()-1:
            self.x = torch.zeros(input_shape, device=self.device)
        elif dist.get_rank() == 0:
            self.dL_dout = torch.zeros(input_shape, device=self.device)
        else:
            self.x = torch.zeros(input_shape, device=self.device)
            self.dL_dout = torch.zeros(input_shape, device=self.device)
        