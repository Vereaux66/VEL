class ANVELRemoteExecutor:
    def __init__(self, async_exec=None, sec_channel=None):
        self.async_exec = async_exec
        self.sec_channel = sec_channel

    def execute(self, command, payload):
        msg = f"{command}:{payload}"
        signed = self.sec_channel.send(msg) if self.sec_channel else {"message": msg}
        if self.async_exec:
            return self.async_exec.submit(lambda: signed["message"])
        return signed

    def verify(self, message, sig):
        return self.sec_channel.verify(message, sig) if self.sec_channel else False
