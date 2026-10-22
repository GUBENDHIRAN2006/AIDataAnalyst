import { ChatMessage, RecordRow } from "@/lib/workspace";

function formatValue(value: unknown): string {
  if (typeof value === "number" && Number.isFinite(value)) {
    return new Intl.NumberFormat(undefined, { maximumFractionDigits: 3 }).format(value);
  }
  if (value === null || value === undefined) return "";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

function ResultsTable({ title, data }: { title: string; data: RecordRow[] }) {
  const columns = Array.from(new Set(data.flatMap((row) => Object.keys(row))));
  if (!columns.length) return null;

  return (
    <section className="result-block">
      <h4>{title}</h4>
      <div className="result-table-wrap">
        <table className="result-table">
          <thead><tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr></thead>
          <tbody>
            {data.map((row, index) => (
              <tr key={index}>
                {columns.map((column) => <td key={column}>{formatValue(row[column])}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Heatmap({ chart }: { chart: Record<string, unknown> }) {
  const columns = Array.isArray(chart.columns)
    ? chart.columns.filter((column): column is string => typeof column === "string")
    : [];
  const matrix = chart.correlation_matrix;
  if (!columns.length || !matrix || typeof matrix !== "object") return null;

  const cellSize = Math.min(54, 500 / columns.length);
  const labelWidth = 120;
  const size = labelWidth + cellSize * columns.length;

  return (
    <div className="chart-scroll">
      <svg
        className="heatmap-chart"
        role="img"
        aria-label="Correlation heatmap"
        viewBox={`0 0 ${size} ${labelWidth + cellSize * columns.length}`}
      >
        {columns.map((column, columnIndex) => (
          <text
            key={`top-${column}`}
            x={labelWidth + columnIndex * cellSize + cellSize / 2}
            y={labelWidth - 8}
            textAnchor="end"
            transform={`rotate(-45 ${labelWidth + columnIndex * cellSize + cellSize / 2} ${labelWidth - 8})`}
            className="chart-label"
          >
            {column}
          </text>
        ))}
        {columns.map((row, rowIndex) => {
          const rowData = (matrix as Record<string, unknown>)[row];
          return (
            <g key={row}>
              <text x={labelWidth - 8} y={labelWidth + rowIndex * cellSize + cellSize * 0.68} textAnchor="end" className="chart-label">{row}</text>
              {columns.map((column, columnIndex) => {
                const raw = rowData && typeof rowData === "object"
                  ? (rowData as Record<string, unknown>)[column]
                  : null;
                const value = typeof raw === "number" && Number.isFinite(raw) ? raw : 0;
                const intensity = Math.min(1, Math.abs(value));
                const fill = value >= 0
                  ? `rgba(81, 70, 229, ${0.12 + intensity * 0.78})`
                  : `rgba(220, 75, 75, ${0.12 + intensity * 0.78})`;
                return (
                  <g key={column}>
                    <rect
                      x={labelWidth + columnIndex * cellSize}
                      y={labelWidth + rowIndex * cellSize}
                      width={cellSize - 2}
                      height={cellSize - 2}
                      rx="4"
                      fill={fill}
                    />
                    <text
                      x={labelWidth + columnIndex * cellSize + cellSize / 2}
                      y={labelWidth + rowIndex * cellSize + cellSize * 0.63}
                      textAnchor="middle"
                      className="heatmap-value"
                    >
                      {value.toFixed(2)}
                    </text>
                  </g>
                );
              })}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function SeriesChart({ chart }: { chart: Record<string, unknown> }) {
  const chartType = typeof chart.chart_type === "string" ? chart.chart_type : "bar";
  const xValues = Array.isArray(chart.x_values) ? chart.x_values : [];
  const yValues = Array.isArray(chart.y_values)
    ? chart.y_values.map((value) => typeof value === "number" && Number.isFinite(value) ? value : 0)
    : [];
  const count = Math.min(xValues.length, yValues.length, 50);
  if (!count) return null;

  const values = yValues.slice(0, count);
  const minimum = Math.min(0, ...values);
  const maximum = Math.max(0, ...values);
  const range = maximum - minimum || 1;
  const width = 760;
  const height = 300;
  const left = 58;
  const right = 18;
  const top = 18;
  const bottom = 62;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;
  const zeroY = top + (maximum / range) * plotHeight;
  const pointX = (index: number) => left + (count === 1 ? plotWidth / 2 : index * plotWidth / (count - 1));
  const pointY = (value: number) => top + ((maximum - value) / range) * plotHeight;
  const points = values.map((value, index) => `${pointX(index)},${pointY(value)}`).join(" ");
  const slotWidth = plotWidth / count;

  return (
    <div className="chart-scroll">
      <svg className="series-chart" role="img" aria-label={`${chartType} chart`} viewBox={`0 0 ${width} ${height}`}>
        {[0, 0.5, 1].map((fraction) => {
          const y = top + fraction * plotHeight;
          const value = maximum - fraction * range;
          return (
            <g key={fraction}>
              <line x1={left} y1={y} x2={width - right} y2={y} className="chart-gridline" />
              <text x={left - 8} y={y + 4} textAnchor="end" className="chart-label">{formatValue(value)}</text>
            </g>
          );
        })}
        {chartType === "bar" ? values.map((value, index) => {
          const y = pointY(value);
          const barY = Math.min(y, zeroY);
          const barHeight = Math.max(1, Math.abs(zeroY - y));
          const barWidth = Math.max(2, slotWidth * 0.66);
          return (
            <rect
              key={index}
              x={pointX(index) - barWidth / 2}
              y={barY}
              width={barWidth}
              height={barHeight}
              rx="3"
              className="chart-bar"
            >
              <title>{`${formatValue(xValues[index])}: ${formatValue(value)}`}</title>
            </rect>
          );
        }) : (
          <>
            {chartType === "line" && <polyline points={points} className="chart-line" />}
            {values.map((value, index) => (
              <circle key={index} cx={pointX(index)} cy={pointY(value)} r="4" className="chart-point">
                <title>{`${formatValue(xValues[index])}: ${formatValue(value)}`}</title>
              </circle>
            ))}
          </>
        )}
        {xValues.slice(0, count).map((value, index) => (
          <text key={index} x={pointX(index)} y={height - bottom + 20} textAnchor="end" transform={`rotate(-35 ${pointX(index)} ${height - bottom + 20})`} className="chart-label">
            {formatValue(value).slice(0, 18)}
          </text>
        ))}
        <text x={left} y={height - 5} className="chart-axis-title">{String(chart.x_column ?? "")}</text>
        <text x="12" y={top} className="chart-axis-title">{String(chart.y_column ?? "")}</text>
      </svg>
    </div>
  );
}

function Histogram({ chart }: { chart: Record<string, unknown> }) {
  const rawValues = Array.isArray(chart.values) ? chart.values : [];
  const values = rawValues.filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  if (!values.length) return <p className="small">No numeric values are available to plot.</p>;

  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const binCount = 10;
  const binSize = maximum === minimum ? 1 : (maximum - minimum) / binCount;
  const counts = Array.from({ length: binCount }, () => 0);
  values.forEach((value) => {
    const index = maximum === minimum ? 0 : Math.min(binCount - 1, Math.floor((value - minimum) / binSize));
    counts[index] += 1;
  });
  return (
    <SeriesChart
      chart={{
        chart_type: "bar",
        x_column: String(chart.x_column ?? "Value"),
        y_column: "Count",
        x_values: counts.map((_, index) => {
          const start = minimum + index * binSize;
          const end = maximum === minimum ? maximum : start + binSize;
          return `${formatValue(start)}–${formatValue(end)}`;
        }),
        y_values: counts,
      }}
    />
  );
}

function Chart({ chart }: { chart: Record<string, unknown> }) {
  const chartType = chart.chart_type;
  const title = typeof chart.title === "string"
    ? chart.title
    : `${String(chartType ?? "Data")} chart`;

  return (
    <section className="result-block">
      <h4>{title}</h4>
      {chartType === "heatmap"
        ? <Heatmap chart={chart} />
        : chartType === "histogram"
          ? <Histogram chart={chart} />
          : <SeriesChart chart={chart} />}
    </section>
  );
}

export default function AnalysisOutput({ message }: { message: ChatMessage }) {
  return (
    <div className="analysis-output">
      {message.content && (
        message.error
          ? <div className="notice error">{message.content}</div>
          : <div className="answer-text">{message.content}</div>
      )}
      {message.tables?.map((table, index) => (
        <ResultsTable key={`${table.title}-${index}`} title={table.title} data={table.data} />
      ))}
      {message.charts?.map((chart, index) => <Chart key={index} chart={chart} />)}
      {message.warnings?.length ? (
        <details className="message-warnings">
          <summary>Analysis notes</summary>
          <ul>{message.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul>
        </details>
      ) : null}
    </div>
  );
}
