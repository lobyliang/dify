from events.app_event import app_was_deleted
from extensions.ext_database import db
from models.dataset import AppDatasetJoin


@app_was_deleted.connect
def handle(sender, **kwargs):
    app = sender
    joined_apps = db.session.query(AppDatasetJoin).filter(AppDatasetJoin.app_id == app.id).all()
    for joined_app in joined_apps:
        db.session.delete(joined_app)
    db.session.commit()