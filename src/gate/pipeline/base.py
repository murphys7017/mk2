from __future__ import annotations

from typing import List, Dict

from ..types import GateStage, GateContext, GateWip, Scene
from ..scene import SceneInferencer
from ..pipeline.hard_bypass import HardBypass
from ..pipeline.feature import FeatureExtractor
from ..pipeline.scoring import ScoringStage
from ..pipeline.dedup import Deduplicator
from ..pipeline.policy import PolicyMapper
from ..pipeline.finalize import FinalizeStage


class PipelineRouter:
    """根据 scene 返回对应的 stage 列表（MVP）"""

    def __init__(self) -> None:
        self._default_pipeline: List[GateStage] = [
            FeatureExtractor(),
            ScoringStage(),
            Deduplicator(),
            PolicyMapper(),
            FinalizeStage(),
        ]

    def get_pipeline(self, scene: Scene) -> List[GateStage]:
        return self._default_pipeline


class DefaultGatePipeline:
    """固定 Gate pipeline 流程"""

    def __init__(self) -> None:
        self.scene_inferencer = SceneInferencer()
        self.hard_bypass = HardBypass()
        self.router = PipelineRouter()

    def run(self, obs, ctx, wip) -> None:
        self.scene_inferencer.apply(obs, ctx, wip)
        self.hard_bypass.apply(obs, ctx, wip)

        pipeline = self.router.get_pipeline(wip.scene or Scene.UNKNOWN)
        for stage in pipeline:
            stage.apply(obs, ctx, wip)
