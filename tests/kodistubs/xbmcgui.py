INPUT_ALPHANUM, INPUT_NUMERIC, ALPHANUM_HIDE_INPUT, NOTIFICATION_INFO = 0, 1, 2, 'info'


class ListItem:
    def __init__(self, label='', label2='', path=''):
        self.label, self.label2, self.path, self.props, self.art = label, label2, path, {}, {}

    def setArt(self, art):
        self.art = art

    def setProperty(self, key, value):
        self.props[key] = value

    def getProperty(self, key):
        return self.props.get(key, '')

    def getMusicInfoTag(self):
        return type('Tag', (), {'setTitle': lambda self, t: None})()


class WindowXML:
    def __init__(self, *args, **kwargs):
        pass


class WindowXMLDialog(WindowXML):
    pass


class Dialog:
    pass


class Window:
    """Attrappe für xbmcgui.Window(10000): Fenstereigenschaften als gemeinsames Wörterbuch."""
    properties = {}

    def __init__(self, window_id):
        self.window_id = window_id

    def getProperty(self, key):
        return Window.properties.get(key, '')

    def setProperty(self, key, value):
        Window.properties[key] = value

    def clearProperty(self, key):
        Window.properties.pop(key, None)
