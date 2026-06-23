'''
Apply kv cache to Transformer decode step
'''

import torch
from torch import nn
import torch.nn.functional as F

class MultiHeadAttentionCross(nn.Module):
    def __init__(self, inMultiHeadAttention: MultiHeadAttention):
        super().__init__()
        self.multiHeadAttention = inMultiHeadAttention

    def forward(
        self,
        x: Tensor,
        k: Tensor,
        v: Tensor,
        mask: Optional[Tensor] = None,
    ):
        q = self.multiHeadAttention.query(x)
        wv, qk = self.multiHeadAttention.qkv_attention(q, k, v, mask)
        return self.multiHeadAttention.out(wv)


class MultiHeadAttentionSelf(nn.Module):
    def __init__(self, inMultiHeadAttention: MultiHeadAttention):
        super().__init__()
        self.multiHeadAttention = inMultiHeadAttention

    def forward(
        self,
        x: Tensor,  # (1, 1      , 384)
        k_cache: Tensor,  # (1, 448, 384)
        v_cache: Tensor,  # (1, 448, 384)
        mask: Tensor,  # (448,)
    ):
        q = self.multiHeadAttention.query(x)  # (1, 1, 384)
        k = self.multiHeadAttention.key(x)  # (1, 1, 384)
        v = self.multiHeadAttention.value(x)  # (1, 1, 384)

        #  k_cache[:, offset : offset + 1, :] = k  # (b, n_ctx_cache + n_ctx, n_state)
        #  v_cache[:, offset : offset + 1, :] = v  # (b, n_ctx_cache + n_ctx, n_state)

        wv, qk = self.multiHeadAttention.qkv_attention_self(
            q,
            k_cache=k_cache,
            v_cache=v_cache,
            k1=k,
            v1=v,
            mask=mask,
        )

        return self.multiHeadAttention.out(wv), k, v


class ResidualAttentionBlockTensorCache(nn.Module):
    def __init__(self, inResidualAttentionBlock: ResidualAttentionBlock):
        super().__init__()
        self.originalBlock = inResidualAttentionBlock
        self.attn = MultiHeadAttentionSelf(inResidualAttentionBlock.attn)
        self.cross_attn = (
            MultiHeadAttentionCross(inResidualAttentionBlock.cross_attn)
            if inResidualAttentionBlock.cross_attn
            else None
        )

    def forward(
        self,
        x: Tensor,
        self_k_cache: Tensor,
        self_v_cache: Tensor,
        cross_k: Tensor,
        cross_v: Tensor,
        offset: Tensor,
        mask: Tensor,
    ):
        self_attn_x, self_k, self_v = self.attn(
            self.originalBlock.attn_ln(x),
            self_k_cache,
            self_v_cache,
            mask=mask,
        )
        x = x + self_attn_x

        if self.cross_attn:
            x = x + self.cross_attn(
                self.originalBlock.cross_attn_ln(x), cross_k, cross_v
            )

        x = x + self.originalBlock.mlp(self.originalBlock.mlp_ln(x))
        return x, self_k, self_v


class TextDecoderTensorCache(nn.Module):
    def __init__(self, inTextDecoder: TextDecoder, in_n_ctx: int):
        super().__init__()
        self.textDecoder = inTextDecoder
        self.n_ctx = in_n_ctx

        self.blocks = []
        for orginal_block in self.textDecoder.blocks:
            self.blocks.append(ResidualAttentionBlockTensorCache(orginal_block))

    def forward(
        self,
        tokens: Tensor,
        self_k: Tensor,
        self_v: Tensor,
        cross_k: Tensor,
        cross_v: Tensor,
        offset: Tensor,
        mask: Tensor,
    ) -> Tuple[Tensor, List[Tuple[Tensor, Tensor]]]:
        """
        tokens: (batch_size, 1)
        self_k self_v: (n_text_layer, batch_size, n_text_ctx, n_text_state)
        cross_k cross_v: (n_audio_layer, batch_size, n_audio_ctx, n_audio_state)
        Returns:
          - logits: (1, 1, n_vocab)
          - this_self_kv_pair
        """
        assert tokens.shape == (1, 1), tokens.shape
        x = self.textDecoder.token_embedding(
            tokens
        ) + self.textDecoder.positional_embedding[offset.to(torch.int64)].unsqueeze(0)

        i = 0
        this_self_k = []
        this_self_v = []
        for block in self.blocks:
            self_k_cache = self_k[i]
            self_v_cache = self_v[i]

            x, update_self_k, update_self_v = block(
                x,
                #  self_k_cache=self_k_cache[:, : offset + 1],
                #  self_v_cache=self_v_cache[:, : offset + 1],
                self_k_cache=self_k_cache,
                self_v_cache=self_v_cache,
                cross_k=cross_k[i],
                cross_v=cross_v[i],
                offset=offset,
                #  mask=self.textDecoder.mask,
                mask=mask,
            )
            #  self_k_cache[:, : offset + 1] = updated_self_k_cache
            #  self_v_cache[:, : offset + 1] = updated_self_v_cache
            #  updated_self_kv_pair.append((self_k_cache, self_v_cache))
            this_self_k.append(update_self_k)
            this_self_v.append(update_self_v)

            i += 1

        x = self.textDecoder.ln(x)

        if False:
            # x.shape (1, 3, 384)
            # weight.shape (51684, 384)

            logits = (
                x
                @ torch.transpose(
                    self.textDecoder.token_embedding.weight.to(x.dtype), 0, 1
                )
            ).float()
        else:
            logits = (
                torch.matmul(
                    self.textDecoder.token_embedding.weight.to(x.dtype),
                    x.permute(0, 2, 1),
                )
                .permute(0, 2, 1)
                .float()
            )

        return logits, torch.stack(this_self_k, dim=0), torch.stack(this_self_v, dim=0)