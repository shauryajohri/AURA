import { MODELS } from "../data/models";

/**
 * The AI models orbiting the black hole. Positioned absolutely around the
 * stage center. `activeId`, when set, force-lights a node (e.g. the model that
 * just answered) - wired to the real router via the bridge.
 */
interface Props {
  activeId?: string | null;
}

export default function ModelConstellation({ activeId = null }: Props) {
  return (
    <div className="constellation">
      {MODELS.map((m) => {
        const status = activeId === m.id ? "active" : m.status;
        return (
          <div
            key={m.id}
            className={"model model--" + status}
            style={{
              left: "calc(50% + " + m.x + "%)",
              top: "calc(50% + " + m.y + "%)",
              ["--accent" as string]: m.color,
            }}
          >
            <span className="model__orb" />
            <div className="model__info">
              <span className="model__name">{m.name}</span>
              <span className="model__role">{m.role}</span>
              <span className={"model__badge model__badge--" + status}>
                {status === "active" ? "ACTIVE" : "STANDBY"}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
