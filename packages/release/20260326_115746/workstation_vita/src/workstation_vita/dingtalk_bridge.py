from __future__ import annotations

import logging
import threading
from collections import deque

from dingtalk_stream.chatbot import ChatbotHandler, ChatbotMessage
from dingtalk_stream.credential import Credential
from dingtalk_stream.frames import AckMessage, CallbackMessage
from dingtalk_stream.stream import DingTalkStreamClient

from workstation_vita.config import get_settings
from workstation_vita.engine import WorkstationEngine


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("workstation_vita.dingtalk")


class MessageDedupe:
    def __init__(self, max_size: int = 1024) -> None:
        self._ids: deque[str] = deque(maxlen=max_size)
        self._set: set[str] = set()
        self._lock = threading.Lock()

    def seen(self, message_id: str) -> bool:
        with self._lock:
            if message_id in self._set:
                return True
            if len(self._ids) == self._ids.maxlen:
                expired = self._ids.popleft()
                self._set.discard(expired)
            self._ids.append(message_id)
            self._set.add(message_id)
            return False


class VitaChatbotHandler(ChatbotHandler):
    def __init__(self, engine: WorkstationEngine) -> None:
        super().__init__()
        self.engine = engine
        self.dedupe = MessageDedupe()

    async def process(self, message: CallbackMessage):
        incoming = ChatbotMessage.from_dict(message.data)
        if self.dedupe.seen(incoming.message_id):
            return AckMessage.STATUS_OK, "重复消息"

        if incoming.conversation_type == "2" and not incoming.is_in_at_list:
            return AckMessage.STATUS_OK, "群聊未艾特，忽略"

        text_list = incoming.get_text_list() or []
        question = "\n".join(text_list).strip()
        if not question:
            self.reply_text("未检测到文本消息。", incoming)
            return AckMessage.STATUS_OK, "空消息"

        try:
            response = self.engine.process_query(question)
            answer = response["answer_markdown"].strip()
            if len(answer) > 3800:
                answer = answer[:3800] + "\n\n[内容已截断]"
            self.reply_markdown(title="VITA", text=answer, incoming_message=incoming)
            return AckMessage.STATUS_OK, "ok"
        except Exception as exc:  # noqa: BLE001
            logger.exception("DingTalk handling failed: %s", exc)
            self.reply_text(f"处理失败：{exc}", incoming)
            return AckMessage.STATUS_SYSTEM_EXCEPTION, str(exc)


def main() -> None:
    settings = get_settings()
    if not settings.dingtalk_client_id or not settings.dingtalk_client_secret:
        raise RuntimeError("缺少钉钉凭证，请配置 VITA_DINGTALK_CLIENT_ID 和 VITA_DINGTALK_CLIENT_SECRET")

    engine = WorkstationEngine()
    credential = Credential(settings.dingtalk_client_id, settings.dingtalk_client_secret)
    client = DingTalkStreamClient(credential)
    client.register_callback_handler(ChatbotMessage.TOPIC, VitaChatbotHandler(engine))
    logger.info("启动钉钉桥接服务")
    client.start_forever()


if __name__ == "__main__":
    main()
