from app.models import (
    AudioRequest,
    AudioSegment,
    PodcastWorkflowApprovalRequest,
)


def build_podcast_audio_request(
    approval: PodcastWorkflowApprovalRequest,
) -> AudioRequest:
    return AudioRequest(
        text="\n\n".join(segment.text for segment in approval.script.segments),
        language_code=approval.language_code,
        voice=approval.host_voice,
        summarize=False,
        audio_format=approval.audio_format,
        segments=[
            AudioSegment(
                speaker=segment.speaker,
                text=segment.text,
                voice=(
                    approval.host_voice
                    if segment.speaker == "host"
                    else approval.guest_voice
                ),
            )
            for segment in approval.script.segments
        ],
    )
