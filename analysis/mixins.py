from analysis.click_image_helpers import ClickImageHelpersMixin
from analysis.click_target_pipeline import ClickTargetPipelineMixin
from analysis.event_unknown_processor import EventUnknownProcessorMixin
from analysis.event_unknown_queue import EventUnknownQueueMixin
from analysis.gpt_yolo_annotation import GptYoloAnnotationMixin
from analysis.llm_click_description import LlmClickDescriptionMixin
from analysis.reanalyze_prompt import ReanalyzePromptMixin
from analysis.reanalyze_providers import ReanalyzeProvidersMixin
from analysis.reanalyze_response import ReanalyzeResponseMixin
from analysis.runtime_index_compile import RuntimeIndexCompileMixin
from analysis.scene_reclassification import SceneReclassificationMixin
from analysis.touch_index_writer import TouchIndexWriterMixin
from analysis.yolo_annotation_files import YoloAnnotationFilesMixin
from analysis.yolo_class_utils import YoloClassUtilsMixin
from analysis.yolo_detection import YoloDetectionMixin
from analysis.yolo_review_actions import YoloReviewActionsMixin
from analysis.yolo_training import YoloTrainingMixin


class AnalysisMixin(
    YoloAnnotationFilesMixin,
    YoloReviewActionsMixin,
    YoloTrainingMixin,
    RuntimeIndexCompileMixin,
    YoloClassUtilsMixin,
    ClickImageHelpersMixin,
    YoloDetectionMixin,
    ClickTargetPipelineMixin,
    LlmClickDescriptionMixin,
    GptYoloAnnotationMixin,
    EventUnknownQueueMixin,
    EventUnknownProcessorMixin,
    TouchIndexWriterMixin,
    ReanalyzePromptMixin,
    ReanalyzeResponseMixin,
    ReanalyzeProvidersMixin,
    SceneReclassificationMixin,
):
    pass
