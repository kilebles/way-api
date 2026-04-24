from enum import StrEnum

from pydantic import BaseModel


class TaskStatus(StrEnum):
    PENDING = "PENDING"
    THROTTLED = "THROTTLED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class TaskOptions(BaseModel):
    name: str
    text_prompt: str
    duration: int = 5  # 5 | 10 | 15
    aspect_ratio: str = "16:9"
    resolution: str = "720p"
    generate_audio: bool = True
    explore_mode: bool = False
    creation_source: str = "tool-mode"
    asset_group_id: str

    model_config = {"populate_by_name": True}

    def to_api(self) -> dict:
        return {
            "name": self.name,
            "textPrompt": self.text_prompt,
            "duration": self.duration,
            "aspectRatio": self.aspect_ratio,
            "resolution": self.resolution,
            "generateAudio": self.generate_audio,
            "exploreMode": self.explore_mode,
            "creationSource": self.creation_source,
            "assetGroupId": self.asset_group_id,
        }


def _parse_error(error: object) -> str | None:
    if error is None:
        return None
    if isinstance(error, str):
        return error or None
    if isinstance(error, dict):
        return error.get("errorMessage") or str(error)
    return str(error)


class Artifact(BaseModel):
    id: str
    url: str


class Task(BaseModel):
    id: str
    name: str
    status: TaskStatus
    progress_ratio: str = "0"
    progress_text: str | None = None
    error: str | None = None
    artifacts: list[Artifact] = []

    model_config = {"populate_by_name": True}

    @classmethod
    def from_api(cls, data: dict) -> "Task":
        t = data["task"]
        artifacts = [Artifact(id=a["id"], url=a["url"]) for a in t.get("artifacts", []) if "url" in a and "id" in a]
        return cls(
            id=t["id"],
            name=t["name"],
            status=TaskStatus(t["status"]),
            progress_ratio=t.get("progressRatio", "0"),
            progress_text=t.get("progressText"),
            error=_parse_error(t.get("error")),
            artifacts=artifacts,
        )
