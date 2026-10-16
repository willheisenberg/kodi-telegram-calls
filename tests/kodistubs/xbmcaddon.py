class Addon:
    def getAddonInfo(self, key):
        return {'id': 'script.telegram.calls', 'path': '/addon', 'profile': '/profile/'}[key]

    def getSettingInt(self, key):
        return 0

    def getSettingString(self, key):
        return ''

    def getSettingBool(self, key):
        return False
