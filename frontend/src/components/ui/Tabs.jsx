export default function Tabs({ tabs, active, onChange }) {
  return (
    <div className="t-tabs">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          className={`t-tab ${active === tab.id ? 't-tab-active' : ''}`}
          onClick={() => onChange(tab.id)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
