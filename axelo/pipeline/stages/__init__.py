from .s1_crawl import CrawlStage
from .s2_fetch import FetchStage
from .s4_static import StaticAnalysisStage
from .s5_dynamic import DynamicAnalysisStage
from .s6_ai_analyze import AIAnalysisStage
from .s7_codegen import CodeGenStage
from .s8_verify import VerifyStage


class DeobfuscateStage:
    def __init__(self, _runner=None) -> None:
        pass

    async def execute(self, _state, _mode, *, bundles):
        from axelo.models.pipeline import StageResult
        return StageResult(stage_name="s3_deobfuscate", success=True, next_input={"bundles": bundles})


__all__ = [
    "CrawlStage",
    "FetchStage",
    "DeobfuscateStage",
    "StaticAnalysisStage",
    "DynamicAnalysisStage",
    "AIAnalysisStage",
    "CodeGenStage",
    "VerifyStage",
]
