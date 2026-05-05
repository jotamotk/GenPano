import {
  ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  ZAxis, ReferenceArea, ReferenceLine, Label
} from 'recharts';

/**
 * CompetitorQuadrantChart — Four-quadrant bubble scatter chart.
 *
 * Used for competitive analysis views (SoV × Sentiment, BCG matrix, etc.)
 * Renders quadrant backgrounds and bubble positions based on x/y/z dimensions.
 *
 * @param {Object} props
 * @param {Array<{name: string, x: number, y: number, z: number, color?: string, isPrimary?: boolean}>} props.data
 * @param {string} props.xLabel - X axis label
 * @param {string} props.yLabel - Y axis label
 * @param {string} props.zLabel - Z (bubble size) label (appears in tooltip)
 * @param {Object} props.quadrantLabels - Labels for each quadrant
 *   @param {string} props.quadrantLabels.topRight
 *   @param {string} props.quadrantLabels.topLeft
 *   @param {string} props.quadrantLabels.bottomRight
 *   @param {string} props.quadrantLabels.bottomLeft
 * @param {number} props.xMidpoint - X axis split point (default: 0.5)
 * @param {number} props.yMidpoint - Y axis split point (default: 0.5)
 * @param {number} props.height - Chart height in px (default: 360)
 * @param {function} props.onBubbleClick - Callback: (item) => void
 * @param {function} props.xFormat - X axis formatter: (v) => string
 * @param {function} props.yFormat - Y axis formatter: (v) => string
 */
export default function CompetitorQuadrantChart({
  data = [],
  xLabel = 'X Axis',
  yLabel = 'Y Axis',
  zLabel = 'Size',
  quadrantLabels = {
    topRight: 'Top Right',
    topLeft: 'Top Left',
    bottomRight: 'Bottom Right',
    bottomLeft: 'Bottom Left',
  },
  xMidpoint = 0.5,
  yMidpoint = 0.5,
  height = 360,
  onBubbleClick,
  xFormat = (v) => v.toFixed(2),
  yFormat = (v) => v.toFixed(2),
  // Bubble radius range in pixels. Small defaults so many bubbles don't overlap.
  bubbleRadius = [8, 24],
  // Show text labels under each bubble (uses payload.name).
  showLabels = true,
}) {
  if (!data || data.length === 0) return null;

  // Determine axis bounds from data
  const xValues = data.map(d => d.x);
  const yValues = data.map(d => d.y);
  const zValues = data.map(d => d.z);

  const xMin = Math.min(...xValues);
  const xMax = Math.max(...xValues);
  const yMin = Math.min(...yValues);
  const yMax = Math.max(...yValues);
  const zMin = Math.min(...zValues);
  const zMax = Math.max(...zValues);

  // Calculate reference line positions (x/y midpoints in absolute coordinates)
  // If midpoints are 0-1 (normalized), scale them to axis range
  const xRefLine = xMidpoint <= 1 ? xMin + (xMax - xMin) * xMidpoint : xMidpoint;
  const yRefLine = yMidpoint <= 1 ? yMin + (yMax - yMin) * yMidpoint : yMidpoint;

  return (
    <ResponsiveContainer width="100%" height={height}>
      <ScatterChart
        data={data}
        margin={{ top: 20, right: 40, bottom: 60, left: 60 }}
      >
        {/* Quadrant backgrounds */}
        <ReferenceArea
          x1={xMin}
          x2={xRefLine}
          y1={yRefLine}
          y2={yMax}
          fill="var(--color-chart-3)"
          fillOpacity={0.06}
          isAnimationActive={false}
        >
          <Label
            value={quadrantLabels.topLeft}
            position="top"
            fill="var(--color-text-muted)"
            fontSize={11}
            offset={8}
          />
        </ReferenceArea>

        <ReferenceArea
          x1={xRefLine}
          x2={xMax}
          y1={yRefLine}
          y2={yMax}
          fill="var(--color-chart-7)"
          fillOpacity={0.06}
          isAnimationActive={false}
        >
          <Label
            value={quadrantLabels.topRight}
            position="top"
            fill="var(--color-text-muted)"
            fontSize={11}
            offset={8}
          />
        </ReferenceArea>

        <ReferenceArea
          x1={xMin}
          x2={xRefLine}
          y1={yMin}
          y2={yRefLine}
          fill="var(--color-chart-line-grid)"
          fillOpacity={0.08}
          isAnimationActive={false}
        >
          <Label
            value={quadrantLabels.bottomLeft}
            position="bottom"
            fill="var(--color-text-muted)"
            fontSize={11}
            offset={8}
          />
        </ReferenceArea>

        <ReferenceArea
          x1={xRefLine}
          x2={xMax}
          y1={yMin}
          y2={yRefLine}
          fill="var(--color-chart-6)"
          fillOpacity={0.06}
          isAnimationActive={false}
        >
          <Label
            value={quadrantLabels.bottomRight}
            position="bottom"
            fill="var(--color-text-muted)"
            fontSize={11}
            offset={8}
          />
        </ReferenceArea>

        {/* Reference lines at midpoints */}
        <ReferenceLine
          x={xRefLine}
          stroke="var(--color-border-subtle)"
          strokeDasharray="4 4"
          strokeWidth={1}
          isAnimationActive={false}
        />
        <ReferenceLine
          y={yRefLine}
          stroke="var(--color-border-subtle)"
          strokeDasharray="4 4"
          strokeWidth={1}
          isAnimationActive={false}
        />

        {/* Axes */}
        <XAxis
          dataKey="x"
          type="number"
          name={xLabel}
          axisLine={false}
          tickLine={false}
          tick={{ fontSize: 11, fill: 'var(--color-chart-axis-text)' }}
          label={{ value: xLabel, position: 'bottom', offset: 20, fontSize: 12, fill: 'var(--color-text-body)' }}
          tickFormatter={xFormat}
          domain={[xMin * 0.95, xMax * 1.05]}
        />

        <YAxis
          dataKey="y"
          type="number"
          name={yLabel}
          axisLine={false}
          tickLine={false}
          tick={{ fontSize: 11, fill: 'var(--color-chart-axis-text)' }}
          label={{ value: yLabel, angle: -90, position: 'insideLeft', offset: -20, fontSize: 12, fill: 'var(--color-text-body)' }}
          tickFormatter={yFormat}
          domain={[yMin * 0.95, yMax * 1.05]}
          width={50}
        />

        {/* Bubble size axis */}
        <ZAxis
          dataKey="z"
          type="number"
          range={[40, 400]}
          name={zLabel}
        />

        {/* Grid */}
        <CartesianGrid
          strokeDasharray="none"
          stroke="var(--color-chart-line-grid)"
          vertical={false}
        />

        {/* Tooltip */}
        <Tooltip
          cursor={{ fill: 'rgba(96, 91, 255, 0.04)' }}
          contentStyle={{
            background: 'var(--color-tooltip-bg)',
            border: '1px solid var(--color-border)',
            borderRadius: 6,
            boxShadow: '0 4px 12px rgba(50,50,93,0.1)',
            fontSize: 12,
            padding: '8px 12px',
          }}
          formatter={(value, name) => {
            if (name === 'x') return [xFormat(value), xLabel];
            if (name === 'y') return [yFormat(value), yLabel];
            if (name === 'z') return [value, zLabel];
            return [value, name];
          }}
          labelFormatter={() => ''}
        />

        {/* Bubbles with custom color per point */}
        <Scatter
          dataKey="y"
          fill="var(--color-chart-line-grid)"
          isAnimationActive={false}
          onClick={(state) => {
            if (onBubbleClick && state.payload) {
              onBubbleClick(state.payload);
            }
          }}
          shape={(props) => {
            const { cx, cy, payload } = props;
            if (cx == null || cy == null || !payload) return null;

            // Get bubble color: primary brand uses accent, others use provided color or default
            const bubbleColor = payload.isPrimary
              ? 'var(--color-accent)'
              : (payload.color || 'var(--color-chart-5)');

            // Map z to the caller-controlled bubbleRadius range using sqrt (area-proportional)
            const z = payload.z || 0;
            const zRange = zMax - zMin || 1;
            const zNorm = Math.sqrt(Math.max(0, (z - zMin) / zRange));
            const [rMin, rMax] = Array.isArray(bubbleRadius) ? bubbleRadius : [8, 24];
            const radius = rMin + zNorm * (rMax - rMin);

            // Label placement: below the bubble with a small gap; truncate long names
            const rawName = typeof payload.name === 'string' ? payload.name : '';
            const label = rawName.length > 10 ? `${rawName.slice(0, 9)}…` : rawName;

            return (
              <g style={{ cursor: onBubbleClick ? 'pointer' : 'default' }}>
                <circle
                  cx={cx}
                  cy={cy}
                  r={radius}
                  fill={bubbleColor}
                  fillOpacity={payload.isPrimary ? 0.85 : 0.55}
                  stroke={payload.isPrimary ? 'var(--color-accent)' : 'var(--color-border-subtle)'}
                  strokeWidth={payload.isPrimary ? 1.5 : 0.75}
                />
                {showLabels && label && (
                  <text
                    x={cx}
                    y={cy + radius + 10}
                    textAnchor="middle"
                    fontSize={10}
                    fontWeight={payload.isPrimary ? 600 : 400}
                    fill={payload.isPrimary ? 'var(--color-accent)' : 'var(--color-text-muted)'}
                    style={{ pointerEvents: 'none' }}
                  >
                    {label}
                  </text>
                )}
              </g>
            );
          }}
        />
      </ScatterChart>
    </ResponsiveContainer>
  );
}
