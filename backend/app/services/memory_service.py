import re
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.db_models import UserMemory

# 记忆权重半衰期:30 天后权重减半,旧偏好自然让位于新偏好
MEMORY_HALF_LIFE_DAYS = 30
MAX_MEMORIES_PER_TYPE = 2

MEMORY_PREFIX = {"preference": "偏好", "avoidance": "避开", "budget": "预算"}

# 语义主题映射:同一主题视为同一记忆槽位,新值写入时旧值失效
MEMORY_TOPIC_KEYWORDS = (
    ("budget", ("预算", "花费", "费用", "多少钱", "省钱")),
    ("food", ("美食", "餐厅", "吃", "小吃", "饮食", "火锅")),
    ("hotel", ("住宿", "酒店", "民宿")),
    ("transport", ("交通", "地铁", "公交", "自驾", "打车", "步行")),
    ("pace", ("节奏", "轻松", "紧凑", "太赶", "行程强度")),
    ("shopping", ("购物", "商场", "买东西")),
    ("attraction", ("景点", "打卡", "博物馆", "公园", "古镇")),
)


def memory_decay_weight(updated_at: datetime | None, now: datetime | None = None) -> float:
    """按最近更新时间计算衰减权重。"""
    if not updated_at:
        return 1.0
    now = now or datetime.utcnow()
    days = max((now - updated_at).days, 0)
    return 0.5 ** (days / MEMORY_HALF_LIFE_DAYS)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text).strip("。！？；,，.；")


def detect_memory_topic(content: str) -> str:
    """从记忆内容中识别语义主题,识别不到时返回空字符串。"""
    for topic, keywords in MEMORY_TOPIC_KEYWORDS:
        if any(keyword in content for keyword in keywords):
            return topic
    return ""


def build_memory_key(memory_type: str, content: str) -> str:
    """生成语义键:同类型同主题归为同一槽位,避免同义偏好重复堆积。

    预算天然是单值槽位;其他类型优先按主题归并,识别不到主题时退回内容本身,
    保证不会把无关偏好错误合并。
    """
    if memory_type == "budget":
        return "budget:budget"
    topic = detect_memory_topic(content)
    return f"{memory_type}:{topic or _normalize(content)[:60]}"


def list_user_memories(db: Session, user_id: int, limit: int = 8) -> list[UserMemory]:
    stmt = (
        select(UserMemory)
        .where(UserMemory.user_id == user_id, UserMemory.is_active.is_(True))
        .order_by(UserMemory.importance.desc(), UserMemory.updated_at.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


def rank_user_memories(db: Session, user_id: int, limit: int = 8) -> list[UserMemory]:
    """按重要度 × 时效衰减排序,并限制同类型条数,避免旧偏好挤占上下文。"""
    memories = list_user_memories(db, user_id, limit=limit * 2)
    ranked = sorted(
        memories,
        key=lambda memory: memory.importance * memory_decay_weight(memory.updated_at),
        reverse=True,
    )
    selected: list[UserMemory] = []
    per_type: dict[str, int] = {}
    for memory in ranked:
        count = per_type.get(memory.memory_type, 0)
        if count >= MAX_MEMORIES_PER_TYPE:
            continue
        per_type[memory.memory_type] = count + 1
        selected.append(memory)
        if len(selected) >= limit:
            break
    return selected


def build_user_memory_context(db: Session, user_id: int) -> str:
    memories = rank_user_memories(db, user_id)
    if not memories:
        return ""
    return "用户长期偏好：" + "；".join(memory.content for memory in memories)


def upsert_user_memory(db: Session, user_id: int, memory_type: str, content: str, importance: int = 2) -> tuple[UserMemory, bool]:
    """按语义键写入记忆。

    - 同槽位同内容:提升重要度并刷新时间,不重复插入
    - 同槽位新内容:旧记忆标记为失效,新记忆生效(冲突时新值优先)
    """
    key = build_memory_key(memory_type, content)
    active_memories = list(
        db.scalars(
            select(UserMemory).where(
                UserMemory.user_id == user_id,
                UserMemory.memory_type == memory_type,
                UserMemory.is_active.is_(True),
            )
        ).all()
    )
    same_slot = [
        memory for memory in active_memories
        if (memory.memory_key or build_memory_key(memory.memory_type, memory.content)) == key
    ]
    for memory in same_slot:
        if _normalize(memory.content) == _normalize(content):
            memory.importance = max(memory.importance, importance)
            memory.updated_at = datetime.utcnow()
            return memory, False
    for memory in same_slot:
        memory.is_active = False
        memory.updated_at = datetime.utcnow()

    memory = UserMemory(
        user_id=user_id,
        memory_type=memory_type,
        memory_key=key,
        content=content,
        importance=importance,
        is_active=True,
    )
    db.add(memory)
    db.flush()
    return memory, True


def _memory_type_for(text: str) -> str:
    if text.startswith(("不要", "别", "不", "避免", "讨厌", "拒绝")):
        return "avoidance"
    if any(word in text for word in ("预算", "花费", "费用", "多少钱")):
        return "budget"
    return "preference"


def extract_preference_memories(content: str) -> list[tuple[str, str]]:
    """用规则从单条消息中抽取结构化记忆(类型, 内容)。"""
    patterns = [
        (r"(?:我|用户)?(?:不喜欢|不要|不想|讨厌|避开)([^。！？；，,]{2,80})", "avoidance"),
        (r"(?:我|用户)?(?<![不没])(?:喜欢|偏好|想要)([^。！？；，,]{2,80})", "preference"),
        (r"(?:预算|花费|费用).{0,20}(?:控制在|不超过|以内)([^。！？；，,]{1,40})", "budget"),
        (r"(?:记住|请记住)([^。！？；，,]{2,80})", None),
        (r"(?:以后|下次|今后)(?:都|要|想|不要|别|不)([^。！？；，,]{1,80})", None),
    ]
    results: list[tuple[str, str]] = []
    for pattern, memory_type in patterns:
        match = re.search(pattern, content)
        if not match:
            continue
        text = match.group(1).strip(" ，,。！？；")
        if len(text) < 2:
            continue
        resolved_type = memory_type or _memory_type_for(text)
        prefix = MEMORY_PREFIX[resolved_type]
        results.append((resolved_type, f"{prefix}：{text}"))
    return results


def remember_preferences_from_message(db: Session, user_id: int, content: str) -> None:
    memories = extract_preference_memories(content)
    if not memories:
        return
    for memory_type, memory_content in memories:
        upsert_user_memory(db, user_id, memory_type, memory_content)
    db.commit()
