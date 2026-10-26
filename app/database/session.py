from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.config import config
from app.database.models import Base

db_url = config.database_url
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}

engine = create_engine(
    db_url,
    connect_args=connect_args,
    pool_pre_ping=True
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)
    from app.database.models import SuppressionRecord, Company
    db = SessionLocal()
    try:
        known = [
            ("voyantixtech.com", "info@voyantixtech.com", "Voyantix"),
            ("datanodes.com", "contact@datanodes.com", "DataNodes"),
            ("nanobi.in", "mahesh@nanobi.in", "nanoBI Analytics")
        ]
        for dom, em, name in known:
            if not db.query(SuppressionRecord).filter(SuppressionRecord.domain == dom).first():
                db.add(SuppressionRecord(domain=dom, email=em, reason="previously_contacted"))
            if not db.query(Company).filter(Company.domain == dom).first():
                db.add(Company(name=name, domain=dom, location="Hyderabad", status="SUPPRESSED"))
        db.commit()
    except Exception as e:
        print(f"[init_db] Warning: {e}")
    finally:
        db.close()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
