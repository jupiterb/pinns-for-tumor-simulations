from typing import Callable, Iterator

from imageprep import ImageData
from imageprep.pipeline.base import Pipeline


class Filter(Pipeline):
    def __init__(
        self, pipeline: Pipeline, predicate: Callable[[ImageData], bool]
    ) -> None:
        self._pipeline = pipeline
        self._predicate = predicate

    def run(self) -> Iterator[ImageData]:
        for item in self._pipeline.run():
            if self._predicate(item):
                yield item
