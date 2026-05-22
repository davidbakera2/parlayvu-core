import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import initialize_database
from app.demo_seed import RAMAIR_PROJECT_ID, seed_ramair_demo
from app.models import AgentEvent, Approval, Client, GeneratedOutput, Project, SourceAsset


class DemoSeedTests(unittest.TestCase):
    def test_ramair_demo_seed_is_idempotent(self):
        engine = create_engine("sqlite:///:memory:")
        initialize_database(engine)
        Session = sessionmaker(bind=engine)

        with Session() as session:
            first = seed_ramair_demo(session)
            session.commit()

        with Session() as session:
            second = seed_ramair_demo(session)
            session.commit()

        self.assertEqual(first["project_id"], RAMAIR_PROJECT_ID)
        self.assertEqual(first["project_id"], second["project_id"])

        with Session() as session:
            project = session.get(Project, RAMAIR_PROJECT_ID)
            self.assertEqual(project.client.name, "RamAir International")
            self.assertEqual(project.metadata_json["teams_channel_pilot"]["artifact_root"], "client_artifacts/ramair")
            self.assertEqual(session.query(Client).count(), 1)
            self.assertEqual(session.query(Project).count(), 1)
            self.assertEqual(session.query(SourceAsset).count(), 2)
            self.assertEqual(session.query(GeneratedOutput).count(), 2)
            self.assertEqual(session.query(Approval).count(), 1)
            self.assertEqual(session.query(AgentEvent).count(), 2)

            artifact_source = (
                session.query(SourceAsset)
                .filter_by(title="RamAir client channel starter artifacts")
                .one()
            )
            self.assertIn("client_artifacts/ramair/nathan-prompts.md", artifact_source.metadata_json["artifact_paths"])

            channel_output = (
                session.query(GeneratedOutput)
                .filter_by(title="RamAir Teams channel pilot kit")
                .one()
            )
            self.assertEqual(channel_output.status, "ready")
            self.assertEqual(channel_output.metadata_json["next_automation"]["name"], "planned_interviews_and_events")


if __name__ == "__main__":
    unittest.main()
