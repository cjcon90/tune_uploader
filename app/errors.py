class UserError(Exception):
    """A problem mum can fix herself; `message` is shown to her as-is."""

    message = ""


class NotMusicXML(UserError):
    message = "This file doesn't look like sheet music. Export it from StaffPad as MusicXML."


class NotAudio(UserError):
    message = "Couldn't read this recording. Try exporting it again."


class TitleTooLong(UserError):
    message = "That title is too long to fit beside the QR code. Try a shorter one."


class BlankTitle(UserError):
    message = "Please give the tune a title."
