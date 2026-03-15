from enum import Enum

class StatusEnum(str, Enum):
    pending = "pending"
    failed = "failed"
    processing = "processing"
    completed = "completed"