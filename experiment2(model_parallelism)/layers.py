from typing import Dict, Optional, Union, Sequence
from abc import ABC, abstractmethod

import torch
from torch import vmap as vmap
import numpy as np

class Layer(ABC):
    def __call__(self, *args, **kwargs):
        return self.forward(*args, **kwargs)
    
    @abstractmethod
    def initial_pass(self):
        pass
        
    @abstractmethod
    def forward(self):
        pass
    
    @abstractmethod
    def backward_p1(self):
        pass
    
    @abstractmethod
    def backward_p2(self):
        #p2 is for calculating param grads if theres no params can just pass
        pass
    


class Dense(Layer):
    def __init__(self, input_size: int, output_size: int):
        """
        Initialize a Dense Layer

        Args:
            input_size (int): size of input vector
            output_size (int): size of output vector
        
        Attributes:
            weights (torch.Tensor): weights of the dense layer
            bias (torch.Tensor): bias of the dense layer
            weights_g (torch.Tensor): gradients of the weights of the dense layer
            bias_g (torch.Tensor): gradients of the bias of the dense layer
            inputs (torch.Tensor): inputs of the dense layer
            dL_dout (torch.Tensor): derivative of the loss with respect to the dense layers output
        
        """
        self.weights = torch.randn(input_size, output_size)
        self.bias = torch.randn(output_size)
        
        self.weights_g = torch.zeros_like(self.weights)
        self.bias_g = torch.zeros_like(self.bias)
    
    def initial_pass(self, x: torch.Tensor):
        """
        Performs an initial forward pass to initialize intermediate tensors

        Args:
            x (torch.Tensor): Input tensor

        Returns:
            torch.Tensor: Output tensor after applying the initial pass of the dense layer
        """
        self.inputs = torch.zeros_like(x)
        x = vmap(lambda x_: torch.mm(x_, self.weights))(x)
        out = torch.add(x, self.bias)
        self.dL_dout = torch.zeros_like(out)
        return out
    
    def forward(self, x: torch.Tensor):
        """
        Performs a forward pass through the dense layer

        Args:
            x (torch.Tensor): Input tensor

        Returns:
            torch.Tensor: Output tensor after applying dense layer
        """
        self.inputs[:] = x
        x =  vmap(lambda x_: torch.mm(x_, self.weights))(x)
        out = torch.add(x, self.bias)
        return out
    
    def backward_p1(self, dL_dout: torch.Tensor):
        """
        Takes the derivative of the loss with respect to the dense layers output and returns the derivative of the loss with respect to the dense layers input

        Args:
            dL_dout (torch.Tensor): Derivative of the loss with respect to the dense layers output

        Returns:
            torch.Tensor: Derivative of the loss with respect to the dense layers input
        """
        self.dL_dout[:] = dL_dout
        return vmap(lambda dl_dout: torch.mm(dl_dout, self.weights.T))(dL_dout)
    
    def backward_p2(self):
        """
        Calculates the gradients of the dense layer's parameters
        """
        self.bias_g[:] = torch.sum(self.dL_dout, dim=tuple(range(self.dL_dout.ndim)[:-1]))
        
        if self.dL_dout.ndim == 2:
            self.weights_g[:] = torch.sum(
                torch.bmm(self.inputs.unsqueeze(2), 
                            self.dL_dout.unsqueeze(1)
                    ),
            dim=0)
        elif self.dL_dout.ndim == 3:
            self.weights_g[:] = torch.sum(
                torch.bmm(
                    torch.transpose(self.inputs, -2, -1),
                    self.dL_dout
                ),
            dim=tuple(range(self.dL_dout.ndim)[:-2]))
        else:
            raise Exception("ndim of input to Dense not supported")


class Relu(Layer):
    def initial_pass(self, x: torch.Tensor):
        """
        Performs an initial forward pass to initialize intermediate tensors

        Args:
            x (torch.Tensor): Input tensor

        Returns:
            torch.Tensor: Output tensor after applying the initial pass of the dense layer
        """
        self.inputs = torch.zeros_like(x)
        return  torch.maximum(x, torch.tensor(0.0, dtype=x.dtype))
    
    def forward(self, x: torch.Tensor):
        """
        Performs a forward pass through the relu

        Args:
            x (torch.Tensor): Input tensor

        Returns:
            torch.Tensor: Output tensor after applying relu
        """
        self.inputs[:] = x
        out = torch.maximum(x, torch.tensor(0.0, dtype=x.dtype))
        return out
    
    def backward_p1(self, dL_dout: torch.Tensor):
        """
        Takes the derivative of the loss with respect to the relus output and returns the derivative of the loss with respect to the relus input

        Args:
            dL_dout (torch.Tensor): Derivative of the loss with respect to the dense layers output

        Returns:
            torch.Tensor: Derivative of the loss with respect to the dense layers input
        """
        dout_din = torch.where(self.inputs>0, 1.0, 0.0)
        return dL_dout*dout_din

    def backward_p2(self):
        pass
    
class Dropout(Layer):
    def __init__(self, p: Optional[float]=0.1):
        """
        Initialize a dropout layer

        Args:
            p (Optional[float]): Probability of neurons being dropped. Defaults to 0.1.
        
        Attributes:
            p (Optional[float]): Probability of neurons being dropped. Defaults to 0.1.
            p_mask (torch.Tensor): Mask for the dropout layer
            training (bool): Turned to False during inference in order to turn off dropout
        """
        self.p = p
        self.training = True
    
    def initial_pass(self, x: torch.Tensor):
        """
        Performs an initial forward pass to initialize intermediate tensors

        Args:
            x (torch.Tensor): Input tensor

        Returns:
            torch.Tensor: Output tensor after applying the initial pass of the dropout
        """
        self.p_mask = torch.bernoulli(torch.ones_like(x) - self.p)
        return x*self.p_mask
    
    def forward(self, x: torch.Tensor):
        """
        Performs a forward pass through the dropout layer. 
        Args:
            x (torch.Tensor): Input Tensor

        Returns:
            torch.Tensor: Output tensor after applying the dropout
        """
        if not self.training or self.p==0:
            return x
        if self.p==1:
            return torch.zeros_like(x)
        self.p_mask[:] = torch.bernoulli(torch.ones_like(x) -self.p)
        return x*self.p_mask
    
    def backward_p1(self, dL_dout: torch.Tensor):
        """
        Takes the derivative of the loss with respect to the dropouts output and returns the derivative of the loss with respect to the dropouts input

        Args:
            dL_dout (torch.Tensor): Derivative of the loss with respect to the dropout's output

        Returns:
            torch.Tensor: Derivative of the loss with respect to the dropout's input
        """
        if self.p==0:
            return dL_dout
        if self.p==1:
            return torch.zeros_like(dL_dout)
        return dL_dout*self.p_mask
    
    def backward_p2(self):
        pass

    
class MultiHeadAttention(Layer):
    #TODO self is the first layer in the model you can cache the linear outputs of the first 3 linears
    def __init__(self, emb_dim: int, num_heads: int, p: Optional[float]=0.1):
        """
        Initializes the multihead attention

        Args:
            emb_dim (int): Size of the embedding dimension
            num_heads (int): Number of attention heads
            p (Optional[float]): Probability for the dropouts. Defaults to 0.1.
        
        Attributes:
            emb_dim (int): Size of the embedding dimension
            num_heads (int): Number of attention heads
            linears (Dict[Dense]): The linear layers in the multi head attention
            dropouts (Dict[Dropout]): The dropouts in the multi head attention
            inputs (Dict[torch.Tensor]): The inputs to the multi head attention
            lQ (torch.Tensor): The linear outputs of the Q linear layer
            lK (torch.Tensor): The linear outputs of the K linear layer
            lV (torch.Tensor): The linear outputs of the V linear layer
            sQK_T (torch.Tensor): The softmax of the QK_T matrix
            device (str): The device the multi head attention is on
            streams (List[torch.cuda.Stream]): The streams used to run backward_p2 on the linear layers in parallel
            dL_dout (torch.Tensor): The derivative of the loss with respect to the multi head attention's output
            weights_g (torch.Tensor): The gradient of the weights of the multi head attention
            bias_g (torch.Tensor): The gradient of the bias of the multi head attention
        """
        self.num_heads = num_heads
        self.emb_dim = emb_dim
        self.linears = {"Q": Dense(self.emb_dim, self.emb_dim),
                        "K": Dense(self.emb_dim, self.emb_dim),
                        "V": Dense(self.emb_dim, self.emb_dim),
                        "O": Dense(self.emb_dim, self.emb_dim)
                        }
        self.dropouts = {"Q": Dropout(p=p),
                         "K": Dropout(p=p),
                         "V": Dropout(p=p)
                        }
    
    def initial_pass(self, Q: torch.Tensor, K: torch.Tensor, V: torch.Tensor, mask: Optional[torch.Tensor]=None):
        """
        Performs an initial forward pass to initialize intermediate tensors

        Args:
            Q (torch.Tensor): Query tensor
            K (torch.Tensor): Key tensor
            V (torch.Tensor): Value tensor
            mask (Optional[torch.Tensor]): Attention mask. Defaults to None.

        Returns:
            torch.Tensor: Output tensor of multihead attention
        """
        #TODO change for multihead
        if "cuda" in str(Q.device):
            self.device = "cuda"
            self.streams = []
            for _ in range(len(self.linears)):
                self.streams.append(torch.cuda.Stream())
        else:
            self.device = "cpu"
        
        self.inputs = {"Q": torch.zeros_like(Q),
                       "K": torch.zeros_like(K),
                       "V": torch.zeros_like(V),
        }
        
        lQ = self.dropouts["Q"].initial_pass(self.linears["Q"].initial_pass(Q))
        lK = self.dropouts["K"].initial_pass(self.linears["K"].initial_pass(K))
        lV = self.dropouts["V"].initial_pass(self.linears["V"].initial_pass(V))
        
        self.lQ = torch.zeros_like(lQ)
        self.lK = torch.zeros_like(lK)
        self.lV = torch.zeros_like(lV)
    
        lQ = torch.cat(lQ.unsqueeze(-2).chunk(self.num_heads, dim=-1), dim=-2)
        lK = torch.cat(lK.unsqueeze(-2).chunk(self.num_heads, dim=-1), dim=-2)
        lV = torch.cat(lV.unsqueeze(-2).chunk(self.num_heads, dim=-1), dim=-2)
        
        QK_T = vmap(lambda q, k: torch.bmm(q, torch.transpose(k, -1, -2)), in_dims=-2, out_dims=-2)(lQ, lK)
        if mask:
            QK_T = vmap(lambda x: x + mask, in_dims=-2, out_dims=-2)(QK_T)
        sQK_T = torch.softmax(QK_T, dim=-1)
        
        self.sQK_T = torch.zeros_like(sQK_T)
        out = vmap(lambda qk_t, v: torch.bmm(qk_t, v), in_dims=-2, out_dims=-2)(sQK_T, lV)
        
        out = torch.flatten(out, -2, -1)
        return self.linears["O"].initial_pass(out)

    
    def forward(self, Q, K, V, mask = None):
        """
        Performs a forward pass through the multihead attention

        Args:
            Q (torch.Tensor): Query tensor
            K (torch.Tensor): Key tensor
            V (torch.Tensor): Value tensor
            mask (Optional[torch.Tensor]): Attention mask. Defaults to None.

        Returns:
            torch.Tensor: Output tensor of multihead attention
        """
        self.inputs["Q"][:] = Q
        self.inputs["K"][:] = K
        self.inputs["V"][:] = V
        
        self.lQ[:] = self.dropouts["Q"](self.linears["Q"](Q))
        self.lK[:] = self.dropouts["K"](self.linears["K"](K))
        self.lV[:] = self.dropouts["V"](self.linears["V"](V))
        
        lQ = torch.cat(self.lQ.unsqueeze(-2).chunk(self.num_heads, dim=-1), dim=-2)
        lK = torch.cat(self.lK.unsqueeze(-2).chunk(self.num_heads, dim=-1), dim=-2)
        lV = torch.cat(self.lV.unsqueeze(-2).chunk(self.num_heads, dim=-1), dim=-2)
        
        QK_T = vmap(lambda q, k: torch.bmm(q, torch.transpose(k, -1, -2)), in_dims=-2, out_dims=-2)(lQ, lK)
        if mask:
            QK_T = vmap(lambda x: x + mask, in_dims=-2, out_dims=-2)(QK_T)
        torch.softmax(QK_T, dim=-1, out=self.sQK_T) #TODO add inplace update
        
        out = vmap(lambda qk_t, v: torch.bmm(qk_t, v), in_dims=-2, out_dims=-2)(self.sQK_T, lV)
        out = torch.flatten(out, -2, -1)
        return self.linears["O"](out)

    
    @staticmethod
    def _softmax_jacobian(softmax_out: torch.Tensor): #softmax_out.shape -> N | 1xN
        """
        Returns the Jacobian of the softmax within the multihead attention

        Args:
            softmax_out (torch.Tensor): The output of the softmax within the multihead attention

        Returns:
            torch.Tensor: The Jacobian of the softmax 
        """
        softmax_out = torch.squeeze(softmax_out)
        n = softmax_out.shape[-1]
        
        jac_base = -softmax_out.view(n, 1) * softmax_out.view(1, n)
        diag = softmax_out*(1-softmax_out)
        jac_base[torch.arange(n), torch.arange(n)] = diag
        
        return jac_base

        
    def backward_p1(self, dL_dout: torch.Tensor):
        """
        Takes the derivative of the loss with respect to the multihead attention output and returns the derivative of the loss with respect to the multihead attention input

        Args:
            dL_dout (torch.Tensor): The derivative of the loss with respect to the multihead attention output

        Returns:
            torch.Tensor: The derivatives of the loss with respect to the multihead attention inputs
        """
        dL_dAtt = self.linears["O"].backward_p1(dL_dout)
        
        dL_dAtt = torch.cat(dL_dAtt.unsqueeze(-2).chunk(self.num_heads, dim=-1), dim=-2)
        
        lV = torch.cat(self.lV.unsqueeze(-2).chunk(self.num_heads, dim=-1), dim=-2)
        dL_dsQKT = vmap(lambda dl_dout, v: torch.bmm(dl_dout, torch.transpose(v, -1,-2)), in_dims=-2, out_dims=-2)(dL_dAtt, lV)
        
        # vmap across 3 dims BxCxH 
        J_sQKT = vmap(vmap(vmap(self._softmax_jacobian)))(self.sQK_T)  # sQK_T.shape -> BxCxHxC 
        dL_dQKT = torch.squeeze(vmap(vmap(vmap(torch.mm)))(dL_dsQKT.unsqueeze(-2), J_sQKT))
        
        lK = torch.cat(self.lK.unsqueeze(-2).chunk(self.num_heads, dim=-1), dim=-2)
        lQ = torch.cat(self.lQ.unsqueeze(-2).chunk(self.num_heads, dim=-1), dim=-2)
        
        # TODO verifiy this section
        dL_dlQ = vmap(lambda dl_dqkt, k: torch.bmm(dl_dqkt, k), in_dims=-2, out_dims=-2)(dL_dQKT, lK)  # k.T not necessary as its k.T.T  
        dL_dlKT = vmap(lambda dl_dqkt, q: torch.bmm(torch.transpose(q, -1,-2), dl_dqkt), in_dims=-2, out_dims=-2)(dL_dQKT, lQ)  
        dL_dlV = vmap(lambda dl_datt, sqkt: torch.bmm(torch.transpose(sqkt, -2, -1), dl_datt), in_dims=-2, out_dims=-2)(dL_dAtt, self.sQK_T) 
        
        dL_dQ = self.linears["Q"].backward_p1(self.dropouts["Q"].backward_p1(torch.flatten(dL_dlQ, -2, -1)))
        dL_dK = self.linears["K"].backward_p1(self.dropouts["K"].backward_p1(torch.flatten(torch.vmap(lambda dl_dlkt: torch.transpose(dl_dlkt, -1, -2), in_dims=-2, out_dims=-2)(dL_dlKT), -2, -1)))
        dL_dV = self.linears["V"].backward_p1(self.dropouts["V"].backward_p1(torch.flatten(dL_dlV, -2, -1)))
        
        return dL_dQ, dL_dK, dL_dV
        
        
    def backward_p2(self): 
        """
        Calculates the gradients of the parameters in the linear layers
        """
        #TODO add sychronize streams within model
        if self.device == "cuda":
            for k, s in zip(self.linears.keys(), self.streams):
                with torch.cuda.stream(s):
                    self.linears[k].backward_p2()
        else:
            for k in self.linears.keys():
                self.linears[k].backward_p2()
                    
class NLPLayerNorm(Layer):
    def __init__(self, dim: int, dim_size: int, eps:Optional[float]=1e-08):
        """
        Initializes the NLP Layer Norm

        Args:
            dim (int): Embedding dim
            dim_size (int): Size of embedding dim
            eps (Optional[float]): eps used to prevent div by 0. Defaults to 1e-08.
        
        Attributes:
            dim (int): Embedding dim
            dim_size (int): Size of embedding dim
            eps (Optional[float]): eps used to prevent div by 0. Defaults to 1e-08.
            gamma (torch.Tensor): gamma parameter
            bias (torch.Tensor): bias parameter
            gamma_g (torch.Tensor): gamma gradient
            bias_g (torch.Tensor): bias gradient
            x_sub_mean (torch.Tensor): x - u
            var (torch.Tensor): variance + eps
            norm_x (torch.Tensor): normalization of x 
            dL_dout (torch.Tensor): the derivative of the loss with respect to the output
        """
        self.dim = dim #seqdim for nlp
        self.dim_size = dim_size
        self.eps = eps
        
        self.gamma = torch.randn(dim_size)
        self.bias = torch.zeros(dim_size)
        
        self.gamma_g = torch.zeros(dim_size)
        self.bias_g = torch.zeros(dim_size)
    
    def initial_pass(self, x: torch.Tensor):
        """
        Performs an initial forward pass through the NLP Layer Norm and generates all intermediates

        Args:
            x (torch.Tensor): Input Tensor

        Returns:
            torch.Tensor: The output of the NLP layer norm
        """
        mean = torch.mean(x, dim=self.dim, keepdim=True)
        x_sub_mean = x-mean
        self.x_sub_mean = torch.zeros_like(x_sub_mean)
        var = torch.mean(torch.square(x_sub_mean), dim=self.dim, keepdim=True) + self.eps
        self.var = torch.zeros_like(var)
        norm_x = (x_sub_mean)/torch.sqrt(var)
        self.norm_x = torch.zeros_like(norm_x)
        self.dL_dout = torch.zeros_like(norm_x)
        return norm_x*self.gamma + self.bias
        
    def forward(self, x: torch.Tensor):
        """
        Performs a forward pass through the NLP Layer Norm

        Args:
            x (torch.Tensor): Input tensor

        Returns:
            torch.Tensor: The output of the NLP layer norm
        """
        mean = torch.mean(x, dim=self.dim, keepdim=True)
        self.x_sub_mean[:] = x-mean
        self.var[:] = torch.mean(torch.square(self.x_sub_mean), dim=self.dim, keepdim=True) + self.eps
        self.norm_x[:] = (self.x_sub_mean)/torch.sqrt(self.var)
        return self.norm_x*self.gamma + self.bias
    
    def _norm_jacobian(self):
        """Returns the Jacobian of the NLP layer norm

        Returns:
            torch.Tensor: The Jacobian of the NLP layer norm
        """
        # F_Jij is pass vectors x,z and scalar v of vector x
        def _F_Jij(x, z, v):
            const_n2 = self.dim_size**2
            f = lambda __x, __z, _v, g: g*((-torch.sqrt(_v)/self.dim_size)-__z*((__x)/const_n2))/_v
            def i_for_j(_x, _z):
                return vmap(f, in_dims=(None, 0, None, 0))(_x, _z, v, self.gamma)
            return vmap(i_for_j, in_dims=(0,None))(x, z)

        def _F_Jii(x, z, v):
            const_n2 = self.dim_size**2
            f = lambda __x, __z, _v, g: g*(((1-1/self.dim_size)*torch.sqrt(_v))-__z*((__x)/const_n2))/_v
            return vmap(f, in_dims=(0,0,None,0))(x, z, v, self.gamma)

        def _diag_set(jac, _diag):
            jac.diagonal()[:]= _diag
            return jac
        
        jac_base = vmap(vmap(_F_Jij))(self.x_sub_mean, self.norm_x,  self.var).squeeze()
        diag = vmap(vmap(_F_Jii))(self.x_sub_mean, self.norm_x, self.var).squeeze()
        return vmap(vmap(_diag_set))(jac_base, diag)
        
        
    def backward_p1(self, dL_dout: torch.Tensor):
        """
        Takes the derivative of the loss with respect to the NLP layer norm output and returns the derivative of the loss with respect to the NLP layer norm input

        Args:
            dL_dout (torch.Tensor): The derivative of the loss with respect to the NLP layer norm output

        Returns:
            torch.Tensor: The derivatives of the loss with respect to the NLP layer norm inputs
        """
        self.dL_dout[:] = dL_dout
        J = self._norm_jacobian()
        return vmap(vmap(torch.mm))(dL_dout.unsqueeze(-2), J).squeeze()

        
    def backward_p2(self):
        """
        Computes the gradients of the parameter in the NLP layer norm
        """
        self.bias_g[:] = torch.sum(dL_dout, dim=tuple(range(self.dL_dout.ndim)[:-1]))
        self.gamma_g[:] = torch.sum(dL_dout*self.norm_x, dim=tuple(range(self.dL_dout.ndim)[:-1]))
      
        
class NLPRMSNorm(Layer):
    def __init__(self, dim: int, dim_size: int, eps: float= 1e-08):
        """
        Initializes the NLP RMS Norm

        Args:
            dim (int): Embedding dim
            dim_size (int): Size of embedding dim
            eps (Optional[float]): eps used to prevent div by 0. Defaults to 1e-08.
        
        Attributes:
            dim (int): Embedding dim
            dim_size (int): Size of embedding dim
            eps (Optional[float]): eps used to prevent div by 0. Defaults to 1e-08.
            weights (torch.Tensor): weights parameter
            weights_g (torch.Tensor): weights gradient
            inputs (torch.Tensor): input tensor
            mean_pow2 (torch.Tensor): mean of x^2
            rms_norm_x (torch.Tensor): rms normalized x
            dL_dout (torch.Tensor): the derivative of the loss with respect to the output
        """
        self.dim = dim #seqdim for nlp
        self.dim_size = dim_size
        self.eps = eps
        
        self.weights = torch.randn(dim_size)
        
        self.weights_g = torch.zeros(dim_size)
    
    def initial_pass(self, x: torch.Tensor):
        """
        Performs an initial forward pass through the NLP RMS norm and generates all intermediates

        Args:
            x (torch.Tensor): Input Tensor

        Returns:
            torch.Tensor: The output of the NLP RMS norm
        """
        self.inputs = torch.zeros_like(x)
        mean_pow2 = torch.mean(x**2, dim=-1, keepdim=True) + self.eps
        self.mean_pow2 = torch.zeros_like(mean_pow2)
        rms_norm_x = x*torch.rsqrt(mean_pow2)
        self.rms_norm_x = torch.zeros_like(rms_norm_x)
        self.dL_dout = torch.zeros_like(rms_norm_x)
        return rms_norm_x*self.weights
    
    def forward(self, x: torch.Tensor):
        """
        Performs a forward pass through the NLP RMS norm

        Args:
            x (torch.Tensor): Input tensor

        Returns:
            torch.Tensor: The output of the NLP RMS norm
        """
        self.inputs[:] = x
        self.mean_pow2[:] = torch.mean(x**2, dim=-1, keepdim=True) + self.eps
        self.rms_norm_x[:] = x*torch.rsqrt(self.mean_pow2)
        return self.rms_norm_x*self.weights
    
    def _rmsnorm_jacobian(self):
        """Returns the Jacobian of the NLP RMS norm

        Returns:
            torch.Tensor: The Jacobian of the NLP RMS norm
        """
        # F_Jij is passed vectors x,z and scalar v of vector x
        def _F_Jij(x,z, mp2):
            f = lambda __x, __z, _mp2, w: w*((-__x*(1/self.dim_size)*__z)/_mp2)
            def i_for_j(_x, _z):
                return vmap(f, in_dims=(None, 0, None, 0))(_x, _z, mp2, self.weights)
            return vmap(i_for_j, in_dims=(0,None))(x, z)

        def _F_Jii(x, z, mp2):
            f = lambda __x, __z, _mp2, w: w*((torch.sqrt(_mp2)-__x*(1/self.dim_size)*__z)/_mp2)
            return vmap(f, in_dims=(0,0,None,0))(x,z,mp2,self.weights)


        def _diag_set(jac, _diag):
            jac.diagonal()[:]= _diag
            return jac
        
        jac_base = vmap(vmap(_F_Jij))(self.inputs, self.rms_norm_x,  self.mean_pow2).squeeze()
        diag = vmap(vmap(_F_Jii))(self.inputs, self.rms_norm_x, self.mean_pow2).squeeze()
        return vmap(vmap(_diag_set))(jac_base, diag)

    def backward_p1(self, dL_dout: torch.Tensor):
        """
        Takes the derivative of the loss with respect to the NLP RMS norm output and returns the derivative of the loss with respect to the NLP RMS norm input

        Args:
            dL_dout (torch.Tensor): The derivative of the loss with respect to the NLP RMS norm output

        Returns:
            torch.Tensor: The derivatives of the loss with respect to the NLP RMS norm inputs
        """
        self.dL_dout[:] = dL_dout
        J = self._norm_jacobian()
        return vmap(vmap(torch.mm))(dL_dout.unsqueeze(-2), J).squeeze()
    
    def backward_p2(self):
        """
        Computes the gradients of the parameter in the NLP layer norm
        """
        self.weights_g[:] = torch.sum(dL_dout*self.rms_norm_x, dim=tuple(range(self.dL_dout.ndim)[:-1]))

        
class BertBlock(Layer):
    def __init__(self, emb_dim: int, num_heads: int, dim_ff:int, activation:Layer=Relu, eps:float=1e-08, p:float=0.1):
        """
        Initialize BERT block

        Args:
            emb_dim (int): size of the embedding dim
            num_heads (int): number of heads in the multihead attention
            dim_ff (int): size of hidden dim in the ffn
            activation (Layer, optional): activation function used on hidden layer in ffn. Defaults to Relu.
            eps (float, optional): the eps used in the layer norms. Defaults to 1e-08.
            p (float, optional): the probability used in the dropouts. Defaults to 0.1.
        
        Attributes:
            multihead (MultiHeadAttention): multihead attention layer
            linears (Dict[Dense]): linear layers
            ff_act (Layer): activation function used on hidden layer in ffn
            norms (Dict[NLPLayerNorm]): layer norms
            dropouts (Dict[Dropout]): dropouts
            device (str): device used for computation
            streams (List[torch.cuda.Stream]): streams used for parallel computation of backward_p2
        """
        self.multihead = MultiHeadAttention(emb_dim=emb_dim, num_heads=num_heads)
        self.linears = {0: Dense(emb_dim, dim_ff),
                        1: Dense(dim_ff, emb_dim)}
        self.ff_act = activation()
        self.norms = {"multi_head": NLPLayerNorm(-1, emb_dim, eps=eps),
                      "ff": NLPLayerNorm(-1, emb_dim, eps=eps)}
        self.dropouts = {"multi_head": Dropout(p=p),
                         "ff": Dropout(p=p)}
    
    def initial_pass(self, x: torch.Tensor):
        """
        Performs an initial pass through the BERT block and generates all intermediates

        Args:
            x (torch.Tensor): Input tensor

        Returns:
            torch.Tensor: Output tensor
        """
        
        if "cuda" in str(x.device):
            self.device = "cuda"
            self.streams = []
            for _ in range(5):  # 5 Layers with parameters
                self.streams.append(torch.cuda.Stream())
        else:
            self.device = "cpu"

        mh_out = self.multihead.initial_pass(x, x, x) + x
        norm_mh_out = self.norms["multi_head"].initial_pass(mh_out)
        norm_mh_out = self.dropouts["multi_head"].initial_pass(norm_mh_out)
        
        ff1 = self.linears[0].initial_pass(norm_mh_out)
        a = self.ff_act.initial_pass(ff1)
        ff2 = self.linears[1].initial_pass(a) + norm_mh_out
        ff2_norm = self.norms["ff"].initial_pass(ff2)
        return self.dropouts["ff"].initial_pass(ff2_norm)
        
    def forward(self, x:torch.Tensor):
        """
        Performs a forward pass through the BERT block. 

        Args:
            x (torch.Tensor): Input tensor

        Returns:
            torch.Tensor: Output tensor of Bert block 
        """
        mh_out = self.multihead(x, x, x) + x
        norm_mh_out = self.norms["multi_head"](mh_out)
        norm_mh_out = self.dropouts["multi_head"](norm_mh_out)
        
        ff1 = self.linears[0](norm_mh_out)
        a = self.ff_act(ff1)
        ff2 = self.linears[1](a) + norm_mh_out
        ff2_norm = self.norms["ff"](ff2)
        return self.dropouts["ff"](ff2_norm)
    
    def backward_p1(self, dL_dout:torch.Tensor):
        """
        Takes the derivative of the loss with respect to the BERT block output and returns the derivative of the loss with respect to the BERT block input

        Args:
            dL_dout (torch.Tensor): Takes the derivative of the loss with respect to the BERT block output 

        Returns:
            torch.Tensor: The derivative of the loss with respect to the BERT block input

        """
        dL_dff2norm = self.dropouts["ff"].backward_p1(dL_dout)
        dL_dff2 = self.norms["ff"].backward_p1(dL_dff2norm)
        dL_da = self.linears[1].backward_p1(dL_dff2)
        dL_dff1 = self.ff_act.backward_p1(dL_da)
        dL_dnormmhout = self.linears[0].backward_p1(dL_dff1) + dL_dout
        
        dL_dnormmhout = self.dropouts["multi_head"].backward_p1(dL_dnormmhout)
        dL_dmhout = self.norms["multi_head"].backward_p1(dL_dnormmhout)
        dL_din1 = torch.sum(torch.stack(self.multihead.backward_p1(dL_dmhout)),dim=0)
        return dL_din1 + dL_dmhout  # dLdmhout == dL_din2
    
    def backward_p2(self):
        """
        Computes the gradients of the parameter in the BERT block
        """
        if "cuda" in str(x.device):
            with torch.cuda.stream(self.streams[0]):
                self.multihead.backward_p2()
                
            for i, s in zip(range(2), self.streams[1:3]):
                with torch.cuda.stream(s):
                    self.linears[i].backward_p2()
            
            for k, s in zip(self.norms.keys(), self.streams[3:]):
                with torch.cuda.stream(s):
                    self.norms[k].backward_p2()
        else:
            self.multihead.backward_p2()
            for i in range(2):
                self.linears[i].backward_p2()
            for k in self.norms.keys():
                self.norms[k].backward_p2()
            
class Conv(Layer):
    def __init__(self, in_channels: int, out_channels: int, k_size: Union[Sequence[int], int], padding: Union[bool, int]=False, stride: Union[Sequence[int], int]=1):
        if isinstance(k_size, int):
            k_size = (k_size, k_size)
        self.kernel = torch.randn(out_channels, in_channels, *k_size)
        self.bias = torch.zeros(out_channels)
        
        self.kernel_g = torch.zeros_like(self.kernel)
        self.bias_g = torch.zeros_like(self.bias)
        
        if isinstance(padding, bool):
            self.padding = 1 if padding else 0
        else:
            self.padding = padding
        
        in_channels_stride_pos = []
        
        if out_channels:
            out_channels_stride_pos = []
        
if __name__ == "__main__":
    x = torch.randn(16, 24, 80)
    dL_dout = torch.randn(16, 24, 80)
    layer = BertBlock(80, 8, 160)
    layer.initial_pass(x)
    layer.forward(x)
    layer.backward_p1(dL_dout)
    layer.backward_p2()
        
        
    