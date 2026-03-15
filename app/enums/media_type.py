from enum import Enum

class MediaTypeEnum(str, Enum):
    image = "image"
    video = "video"

class MediaStatus(str, Enum):
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    DONE = "DONE"
    ERROR = "ERROR"
    DELETED = "DELETED"