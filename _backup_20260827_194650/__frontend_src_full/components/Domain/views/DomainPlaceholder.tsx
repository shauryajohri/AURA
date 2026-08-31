// Elegant placeholder for surfaces still condensing into existence.

interface Props {
  icon: string;
  title: string;
  line: string;
}

export default function DomainPlaceholder({ icon, title, line }: Props) {
  return (
    <div className="dph">
      <div className="dph__icon">{icon}</div>
      <h3>{title}</h3>
      <p>{line}</p>
      <div className="dph__pulse" />
    </div>
  );
}
