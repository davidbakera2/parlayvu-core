import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import initialize_database
from app.models import AgentEvent, Approval, Client, GeneratedOutput, Project, SourceAsset


class ProjectMemoryModelTests(unittest.TestCase):
    def test_project_memory_schema_supports_core_workflow(self):
        engine = create_engine("sqlite:///:memory:")
        initialize_database(engine)
        Session = sessionmaker(bind=engine)

        with Session() as session:
            client = Client(
                id="ramair",
                name="RamAir",
                brand_voice_summary="Practical, expert, and sales-supportive",
            )
            project = Project(
                id="straight-from-the-hart",
                client=client,
                name="Straight from the Hart",
                objective="Turn each episode into a coordinated content engine.",
            )
            source = SourceAsset(
                project=project,
                asset_type="video_podcast",
                title="Episode 1",
                uri="https://example.com/episode-1",
                summary="A source episode for repurposing.",
            )
            output = GeneratedOutput(
                project=project,
                source_asset=source,
                agent_name="dylan",
                output_type="landing_page",
                title="Episode landing page",
                status="draft",
            )
            approval = Approval(
                project=project,
                generated_output=output,
                requested_by_agent="nathan",
                status="pending",
            )
            event = AgentEvent(
                project=project,
                client=client,
                agent_name="nathan",
                event_type="route_decision",
                channel="teams",
                summary="Nathan routed the landing page build to Dylan.",
            )

            session.add_all([client, project, source, output, approval, event])
            session.commit()

            stored_project = session.get(Project, "straight-from-the-hart")
            self.assertEqual(stored_project.client.name, "RamAir")
            self.assertEqual(len(stored_project.source_assets), 1)
            self.assertEqual(stored_project.generated_outputs[0].agent_name, "dylan")
            self.assertEqual(stored_project.approvals[0].status, "pending")
            self.assertEqual(stored_project.agent_events[0].channel, "teams")


if __name__ == "__main__":
    unittest.main()
