from __future__ import annotations

import torch as th
from torch import nn
from typing import Generic, Sequence

from phynn.nn.base import NNBlockParams, NNBuilder
from phynn.nn.fc import FC, FCBlockParams


class AutoEncoder(nn.Module):
    def __init__(
        self,
        in_shape: Sequence[int],
        encoder: nn.Module,
        decoder: nn.Module,
    ) -> None:
        super(AutoEncoder, self).__init__()
        self._in_shape = in_shape
        self._encoder = encoder
        self._decoder = decoder

    @property
    def in_shape(self) -> Sequence[int]:
        return self._in_shape

    @property
    def encoder(self) -> nn.Module:
        return self._encoder

    @property
    def decoder(self) -> nn.Module:
        return self._decoder

    def add_inner(self, inner: AutoEncoder) -> AutoEncoder:
        self._encoder = nn.Sequential(self._encoder, inner.encoder)
        self._decoder = nn.Sequential(inner.decoder, self._decoder)
        return self

    def flatten(self) -> AutoEncoder:
        with th.no_grad():
            latent_shape = self._encoder(th.zeros((1, *self._in_shape))).shape[1:]

        self._encoder = nn.Sequential(self._encoder, nn.Flatten())
        self._decoder = nn.Sequential(nn.Unflatten(1, latent_shape), self._decoder)

        return self

    def forward(self, x: th.Tensor) -> th.Tensor:
        latent = self._encoder(x)
        return self._decoder(latent)


class AutoEncoderBuilder(AutoEncoder, Generic[NNBlockParams]):
    def __init__(
        self,
        in_shape: Sequence[int],
        encoder_builder: NNBuilder[NNBlockParams],
        decoder_builder: NNBuilder[NNBlockParams],
    ) -> None:
        super().__init__(in_shape, encoder_builder.nn, decoder_builder.nn)
        self._encoder_builder = encoder_builder
        self._decoder_builder = decoder_builder

    def add_block(self, params: NNBlockParams) -> AutoEncoderBuilder:
        self._encoder_builder.append(params)
        self._decoder_builder.prepend(params)
        return self


class _VariationalEncoder(nn.Module):
    def __init__(
        self, encoder: nn.Module, pre_latent_size: int, latent_size: int
    ) -> None:
        super(_VariationalEncoder, self).__init__()
        self._encoder = encoder
        self._fc_mu = nn.Linear(pre_latent_size, latent_size)
        self._fc_var = nn.Linear(pre_latent_size, latent_size)

    def forward(self, x: th.Tensor) -> tuple[th.Tensor, th.Tensor]:
        x = self._encoder(x)
        return self._fc_mu(x), self._fc_var(x)


class _VariationalDecoder(nn.Module):
    def __init__(
        self, decoder: nn.Module, pre_latent_size: int, latent_size: int
    ) -> None:
        super(_VariationalDecoder, self).__init__()
        pre_decoder_fc = FC(latent_size).append(FCBlockParams(pre_latent_size)).nn
        self._decoder = nn.Sequential(pre_decoder_fc, decoder)

    def forward(self, mu: th.Tensor, log_var: th.Tensor) -> th.Tensor:
        std = th.exp(0.5 * log_var)
        latent = mu + std * th.randn(mu.size())
        return self._decoder(latent)


class VariationalAutoEncoder(AutoEncoder):
    def __init__(
        self,
        in_shape: Sequence[int],
        encoder: nn.Module,
        decoder: nn.Module,
        latent_size: int,
    ) -> None:
        with th.no_grad():
            pre_latent_shape = encoder(th.zeros((1, *in_shape)))[1:]

        if len(pre_latent_shape) > 1:
            raise ValueError(
                f"Encoder output should be flat, but is {pre_latent_shape}."
            )

        pre_latent_size = pre_latent_shape[0]

        encoder = _VariationalEncoder(encoder, pre_latent_size, latent_size)
        decoder = _VariationalDecoder(decoder, pre_latent_size, latent_size)

        super().__init__(in_shape, encoder, decoder)