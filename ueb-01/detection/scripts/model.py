"""Two-headed MobileNetV3-small classifier (age band + gender).

Shared by ``train.py`` (training) and ``export_onnx.py`` (loading the best
checkpoint for ONNX export). The backbone is ``mobilenet_v3_small`` with its
classifier replaced by two independent linear heads that share the pooled
backbone features.
"""

from __future__ import annotations

import torch
import torch.nn as nn
import torchvision

from common import AGE_BANDS, GENDERS


class AudienceClassifier(nn.Module):
    """MobileNetV3-small backbone with an age head (5) and a gender head (2)."""

    def __init__(self, pretrained: bool = True, dropout: float = 0.2) -> None:
        super().__init__()
        weights = (
            torchvision.models.MobileNet_V3_Small_Weights.DEFAULT if pretrained else None
        )
        backbone = torchvision.models.mobilenet_v3_small(weights=weights)
        # features -> avgpool -> classifier. We keep features+avgpool, replace head.
        self.features = backbone.features
        self.avgpool = backbone.avgpool
        # MobileNetV3-small: classifier[0] is Linear(in=576, out=1024).
        in_features = backbone.classifier[0].in_features
        hidden = backbone.classifier[0].out_features

        self.shared = nn.Sequential(
            nn.Linear(in_features, hidden),
            nn.Hardswish(inplace=True),
            nn.Dropout(p=dropout, inplace=False),
        )
        self.age_head = nn.Linear(hidden, len(AGE_BANDS))
        self.gender_head = nn.Linear(hidden, len(GENDERS))

    def forward(self, x: torch.Tensor):
        x = self.features(x)
        x = self.avgpool(x)
        x = torch.flatten(x, 1)
        x = self.shared(x)
        age_logits = self.age_head(x)
        gender_logits = self.gender_head(x)
        return age_logits, gender_logits

    def backbone_parameters(self):
        """Parameters belonging to the (freezable) feature extractor."""
        yield from self.features.parameters()

    def set_backbone_requires_grad(self, requires: bool) -> None:
        for p in self.features.parameters():
            p.requires_grad = requires
