<?php

namespace Dashboard\Api;

use Dashboard\Services\MetricsService;
use Dashboard\Services\ReportService;
use Dashboard\Auth\JwtGuard;
use Dashboard\Http\JsonResponse;

#[Route('/api/metrics')]
class AnalyticsController
{
    private MetricsService $metrics;
    private ReportService $reports;
    private JwtGuard $guard;

    public function __construct(
        MetricsService $metrics,
        ReportService $reports,
        JwtGuard $guard
    ) {
        $this->metrics = $metrics;
        $this->reports = $reports;
        $this->guard   = $guard;
    }

    #[Get]
    public function getMetrics(array $query): JsonResponse
    {
        $user = $this->guard->authenticate();
        $from = new \DateTime($query['from'] ?? '-7 days');
        $to   = new \DateTime($query['to']   ?? 'now');

        $data = $this->metrics->aggregate($user->orgId(), $from, $to);
        return JsonResponse::ok($data);
    }

    #[Get('/chart')]
    public function getChart(array $query, string $key): JsonResponse
    {
        $this->guard->authenticate();
        $from = new \DateTime($query['from'] ?? '-30 days');
        $to   = new \DateTime($query['to']   ?? 'now');

        $chart = $this->metrics->chartData($key, $from, $to);
        return JsonResponse::ok($chart);
    }

    #[Post('/export')]
    public function exportReport(array $body): mixed
    {
        $user   = $this->guard->authenticate();
        $format = $body['format'] ?? 'csv';
        $from   = new \DateTime($body['from'] ?? '-7 days');
        $to     = new \DateTime($body['to']   ?? 'now');

        $blob = $this->reports->generate($user->orgId(), $from, $to, $format);
        return response()->download($blob, "report.$format");
    }

    private function validateDateRange(\DateTime $from, \DateTime $to): void
    {
        if ($from >= $to) {
            throw new \InvalidArgumentException('"from" must be before "to"');
        }
        $maxDays = 365;
        $diff = $to->diff($from)->days;
        if ($diff > $maxDays) {
            throw new \InvalidArgumentException("Date range exceeds $maxDays days");
        }
    }
}

class MetricsService
{
    private $db;
    private array $cache = [];

    public function __construct($db)
    {
        $this->db = $db;
    }

    public function aggregate(int $orgId, \DateTime $from, \DateTime $to): array
    {
        $cacheKey = "$orgId:{$from->getTimestamp()}:{$to->getTimestamp()}";
        if (isset($this->cache[$cacheKey])) {
            return $this->cache[$cacheKey];
        }

        $raw  = $this->db->query(
            'SELECT metric_key, SUM(value) as total, AVG(value) as avg
             FROM metrics WHERE org_id = ? AND recorded_at BETWEEN ? AND ?
             GROUP BY metric_key',
            [$orgId, $from->format('Y-m-d'), $to->format('Y-m-d')]
        );

        $result = $this->buildMetricPayload($raw, $from, $to);
        $this->cache[$cacheKey] = $result;
        return $result;
    }

    public function chartData(string $key, \DateTime $from, \DateTime $to): array
    {
        $rows = $this->db->query(
            'SELECT DATE(recorded_at) as date, SUM(value) as total
             FROM metrics WHERE metric_key = ? AND recorded_at BETWEEN ? AND ?
             GROUP BY DATE(recorded_at) ORDER BY date ASC',
            [$key, $from->format('Y-m-d'), $to->format('Y-m-d')]
        );
        return [
            'labels'   => array_column($rows, 'date'),
            'datasets' => [['label' => $key, 'data' => array_column($rows, 'total')]],
        ];
    }

    private function buildMetricPayload(array $raw, \DateTime $from, \DateTime $to): array
    {
        $payload = [];
        foreach ($raw as $row) {
            $prev  = $this->getPrevious($row['metric_key'], $from, $to);
            $delta = $prev > 0 ? (($row['total'] - $prev) / $prev) * 100 : 0;
            $payload[] = [
                'key'           => $row['metric_key'],
                'value'         => round($row['total'], 2),
                'avg'           => round($row['avg'], 2),
                'changePercent' => round($delta, 1),
                'trend'         => $delta > 0 ? 'up' : ($delta < 0 ? 'down' : 'flat'),
            ];
        }
        return $payload;
    }

    private function getPrevious(string $key, \DateTime $from, \DateTime $to): float
    {
        $span = $to->getTimestamp() - $from->getTimestamp();
        $prevTo   = (clone $from);
        $prevFrom = (clone $from)->modify("-{$span} seconds");

        $row = $this->db->queryOne(
            'SELECT SUM(value) as total FROM metrics
             WHERE metric_key = ? AND recorded_at BETWEEN ? AND ?',
            [$key, $prevFrom->format('Y-m-d'), $prevTo->format('Y-m-d')]
        );
        return (float)($row['total'] ?? 0);
    }

    public function clearCache(): void
    {
        $this->cache = [];
    }
}
