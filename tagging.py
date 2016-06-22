from mutagen.id3 import ID3, TIT2, TPE1, TCON


# Collection of fields and their corresponding ID3 frames
# Use lowercase for field names
FIELDS = {
    'title': TIT2,
    'artist': TPE1,
    'genre': TCON
}


def apply_tags(tags, path):
    # Check if tag argument is a list of Tag objects
    if len(tags) > 1:
        for tag in tags:
            if not type(tag) == Tag:
                raise ValueError('Tags argument must consist of Tag objects')
    else:
        if not type(tags) == Tag:
            raise ValueError('Tags argument must consist of Tag objects')

    # Create ID3 object
    # We're using ID3v2.3 because some apps don't support v2.4 (such as MS File Explorer)
    audio = ID3(path, v2_version=3)

    # Add tags to ID3 object
    for tag in tags:
        # Don't add tag if value is None or whitespace
        if tag.value is not None and not tag.value.isspace():
            audio.add(tag.frame(text=tag.value))

    # Write tags to file
    audio.save(v2_version=3)


class Tag:
    def __init__(self, fieldname, value):
        # Store fieldname
        self.fieldname = fieldname

        # Select correct frame from field name
        if fieldname.lower() in FIELDS:
            self.frame = FIELDS[fieldname.lower()]
        else:
            raise ValueError('Not a valid field name')

        # Set the value of the tag
        self.value = value
