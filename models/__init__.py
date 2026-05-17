from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

from models.user import User  # noqa: E402, F401
from models.payment import Payment  # noqa: E402, F401
from models.schedule import Schedule, StudentSchedule  # noqa: E402, F401
from models.class_model import ClassSession  # noqa: E402, F401
from models.notification import Notification  # noqa: E402, F401
from models.community import CommunityPost, Comment, PostLike  # noqa: E402, F401
from models.admin_action import AdminAction  # noqa: E402, F401
from models.academy_settings import AcademySettings  # noqa: E402, F401
