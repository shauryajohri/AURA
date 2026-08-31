import { useDomainStore } from "../../../stores/domainStore";

// Every brain view needs the same answer to "nothing is selected yet".
export default function NoProject({ what }: { what: string }) {
  const setSection = useDomainStore((s) => s.setSection);
  return (
    <div className="brempty brempty--big">
      <span className="brempty__icon">◈</span>
      <h3>No project open</h3>
      <p>Pick or create a project first — then you can {what}.</p>
      <button className="brbtn brbtn--go" onClick={() => setSection("projects")}>
        Go to Projects
      </button>
    </div>
  );
}
