/**
 * Analytics dashboard — TypeScript core module.
 */

import { ApiError, get, post } from './api_client';

export interface Metric {
    key: string;
    value: number;
    unit: string;
    trend: 'up' | 'down' | 'flat';
    changePercent: number;
}

export interface ChartData {
    labels: string[];
    datasets: { label: string; data: number[]; color: string }[];
}

export type DateRange = { from: Date; to: Date };

const REFRESH_INTERVAL_MS = 30_000;
const MAX_DATA_POINTS = 90;

// ---------------------------------------------------------------------------
// Data fetching
// ---------------------------------------------------------------------------

async function fetchMetrics(range: DateRange): Promise<Metric[]> {
    const params = new URLSearchParams({
        from: range.from.toISOString(),
        to:   range.to.toISOString(),
    });
    return get(`/metrics?${params}`);
}

async function fetchChartData(metricKey: string, range: DateRange): Promise<ChartData> {
    return get(`/metrics/${metricKey}/chart?from=${range.from.toISOString()}&to=${range.to.toISOString()}`);
}

async function exportReport(range: DateRange, format: 'csv' | 'pdf' = 'csv'): Promise<Blob> {
    const response = await fetch(`/api/reports/export?format=${format}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ from: range.from, to: range.to }),
    });
    if (!response.ok) throw new ApiError(response.status, 'Export failed');
    return response.blob();
}

// ---------------------------------------------------------------------------
// Metric card component
// ---------------------------------------------------------------------------

class MetricCard {
    private element: HTMLElement;
    private metric: Metric;

    constructor(containerId: string, metric: Metric) {
        this.element = document.getElementById(containerId)!;
        this.metric  = metric;
    }

    render(): void {
        const trendIcon = this.metric.trend === 'up' ? '▲' : this.metric.trend === 'down' ? '▼' : '—';
        const trendClass = `trend-${this.metric.trend}`;
        this.element.innerHTML = `
            <div class="metric-card">
                <span class="metric-label">${this.metric.key}</span>
                <span class="metric-value">${this.metric.value}${this.metric.unit}</span>
                <span class="${trendClass}">${trendIcon} ${Math.abs(this.metric.changePercent)}%</span>
            </div>
        `;
    }

    update(newMetric: Metric): void {
        this.metric = newMetric;
        this.render();
    }

    getValue(): number {
        return this.metric.value;
    }
}

// ---------------------------------------------------------------------------
// Chart renderer
// ---------------------------------------------------------------------------

class LineChart {
    private canvas: HTMLCanvasElement;
    private ctx: CanvasRenderingContext2D;
    private data: ChartData | null = null;

    constructor(canvasId: string) {
        this.canvas = document.getElementById(canvasId) as HTMLCanvasElement;
        this.ctx = this.canvas.getContext('2d')!;
    }

    setData(data: ChartData): void {
        this.data = data;
        this.draw();
    }

    private draw(): void {
        if (!this.data) return;
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        this.drawAxes();
        this.data.datasets.forEach(ds => this.drawLine(ds));
    }

    private drawAxes(): void {
        const { width, height } = this.canvas;
        this.ctx.strokeStyle = '#e2e8f0';
        this.ctx.lineWidth = 1;
        this.ctx.beginPath();
        this.ctx.moveTo(40, 10);
        this.ctx.lineTo(40, height - 30);
        this.ctx.lineTo(width - 10, height - 30);
        this.ctx.stroke();
    }

    private drawLine(dataset: { label: string; data: number[]; color: string }): void {
        const { width, height } = this.canvas;
        const max  = Math.max(...dataset.data, 1);
        const xStep = (width - 50) / Math.max(dataset.data.length - 1, 1);
        const yScale = (height - 40) / max;

        this.ctx.strokeStyle = dataset.color;
        this.ctx.lineWidth   = 2;
        this.ctx.beginPath();
        dataset.data.forEach((v, i) => {
            const x = 40 + i * xStep;
            const y = height - 30 - v * yScale;
            i === 0 ? this.ctx.moveTo(x, y) : this.ctx.lineTo(x, y);
        });
        this.ctx.stroke();
    }
}

// ---------------------------------------------------------------------------
// Dashboard controller
// ---------------------------------------------------------------------------

class Dashboard {
    private range: DateRange;
    private cards: Map<string, MetricCard> = new Map();
    private charts: Map<string, LineChart> = new Map();
    private refreshTimer: number | null = null;

    constructor(defaultRange?: DateRange) {
        const now = new Date();
        this.range = defaultRange ?? {
            from: new Date(now.getTime() - 7 * 24 * 3600_000),
            to:   now,
        };
    }

    async init(): Promise<void> {
        await this.loadAllMetrics();
        this.startAutoRefresh();
    }

    async loadAllMetrics(): Promise<void> {
        try {
            const metrics = await fetchMetrics(this.range);
            metrics.forEach(m => {
                const card = this.cards.get(m.key);
                if (card) card.update(m);
            });
        } catch (err) {
            console.error('Failed to load metrics:', err);
        }
    }

    registerCard(key: string, containerId: string, initialMetric: Metric): MetricCard {
        const card = new MetricCard(containerId, initialMetric);
        this.cards.set(key, card);
        card.render();
        return card;
    }

    registerChart(key: string, canvasId: string): LineChart {
        const chart = new LineChart(canvasId);
        this.charts.set(key, chart);
        return chart;
    }

    setDateRange(range: DateRange): void {
        this.range = range;
        this.loadAllMetrics();
    }

    startAutoRefresh(): void {
        this.refreshTimer = window.setInterval(() => this.loadAllMetrics(), REFRESH_INTERVAL_MS);
    }

    stopAutoRefresh(): void {
        if (this.refreshTimer !== null) {
            clearInterval(this.refreshTimer);
            this.refreshTimer = null;
        }
    }

    async downloadReport(format: 'csv' | 'pdf'): Promise<void> {
        const blob = await exportReport(this.range, format);
        const url  = URL.createObjectURL(blob);
        const a    = document.createElement('a');
        a.href     = url;
        a.download = `report.${format}`;
        a.click();
        URL.revokeObjectURL(url);
    }
}

export { Dashboard, MetricCard, LineChart, fetchMetrics, fetchChartData, exportReport };
