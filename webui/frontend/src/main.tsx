import React, { useEffect, useMemo, useState } from 'react';
import ReactDOM from 'react-dom/client';
import {
  App as AntApp,
  Button,
  ConfigProvider,
  Descriptions,
  Empty,
  Flex,
  Segmented,
  Select,
  Space,
  Tabs,
  Tag,
  Typography,
  theme,
} from 'antd';
import {
  ArrowRightOutlined,
  AppstoreOutlined,
  BarChartOutlined,
  CheckCircleOutlined,
  DatabaseOutlined,
  LinkOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { PageContainer, ProCard, ProLayout, ProTable } from '@ant-design/pro-components';
import type { ProColumns } from '@ant-design/pro-components';
import 'antd/dist/reset.css';
import './styles.css';

type Task = {
  task_id: number;
  business_context: string;
  site_url: string;
  host: string;
  data_kind: string;
  crawl_mode: string;
  scope_mode: string;
  max_pages_per_run?: number;
  politeness_rps: number;
  created_by?: string;
  created_at: string;
  status: string;
  generation_status: 'pending' | 'claimed' | 'drafting' | 'sandbox_test' | 'pr_open' | 'merged' | 'failed';
  raw_count: number;
  url_count: number;
  fetch_count: number;
  adapter_ready: boolean;
};

type UrlRecord = {
  url_fp: string;
  url: string;
  depth: number;
  parent_url_fp?: string;
  discovery_source?: string;
  frontier_state: string;
  status_code?: number;
  error_kind?: string;
  fetched_at?: string;
  link_kind: 'fetched' | 'jump';
  raw_id?: number;
  raw_title?: string;
  raw_excerpt?: string;
};

type DepthSummary = Array<{ depth: number; url_count: number }>;
type UrlTabKey = 'all' | 'collected' | 'uncollected';

type Adapter = {
  business_context: string;
  host: string;
  data_kind: string;
  schema_version: number;
  render_mode: string;
  last_verified_at: string;
  module_path: string;
};

type RawItem = {
  id: number;
  task_id: number;
  business_context: string;
  host: string;
  url: string;
  raw_blob_uri: string;
  created_at: string;
  title: string;
  body_text: string;
  source_metadata: Record<string, unknown>;
  attachments: Array<{ url: string; filename?: string | null; mime?: string | null }>;
  child_links: ChildLink[];
};

type ChildLink = {
  url: string;
  depth?: number | null;
  discovery_source?: string;
  frontier_state: string;
  status_code?: number | null;
  error_kind?: string | null;
  raw_id?: number | null;
  link_type: 'attachment' | 'interpret' | 'link';
  filename?: string | null;
  mime?: string | null;
};

type RouteState =
  | { name: 'tasks' }
  | { name: 'task'; taskId: number }
  | { name: 'item'; taskId: number; itemId: number }
  | { name: 'adapters' }
  | { name: 'monitor' };

async function api<T>(path: string): Promise<T> {
  const response = await fetch(path, { headers: { 'X-Requested-With': 'webui' } });
  if (!response.ok) throw new Error(`${path} ${response.status}`);
  return response.json() as Promise<T>;
}

function parseRoute(): RouteState {
  const path = window.location.pathname.replace(/^\/ui/, '') || '/tasks';
  const itemMatch = path.match(/^\/tasks\/(\d+)\/items\/(\d+)$/);
  if (itemMatch) {
    return { name: 'item', taskId: Number(itemMatch[1]), itemId: Number(itemMatch[2]) };
  }
  const taskMatch = path.match(/^\/tasks\/(\d+)$/);
  if (taskMatch) return { name: 'task', taskId: Number(taskMatch[1]) };
  if (path === '/adapters') return { name: 'adapters' };
  if (path === '/monitor') return { name: 'monitor' };
  return { name: 'tasks' };
}

function navigate(path: string) {
  window.history.pushState(null, '', `/ui${path}`);
  window.dispatchEvent(new PopStateEvent('popstate'));
}

function StatusTag({ value }: { value: string }) {
  const color = value === 'done' || value === 'completed'
    ? 'green'
    : value === 'failed' || value === 'disabled'
      ? 'red'
      : value === 'pending' || value === 'scheduled'
        ? 'blue'
        : 'gold';
  return <Tag color={color}>{value}</Tag>;
}

function compactUrl(value: string): string {
  try {
    const parsed = new URL(value);
    const path = `${parsed.pathname}${parsed.search}`;
    return `${parsed.host}${path}`;
  } catch {
    return value;
  }
}

function MetricCell({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="metric-cell">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

type DataTableProps<T> = {
  rowKey: string;
  loading?: boolean;
  dataSource: T[];
  columns: ProColumns<T>[];
  total: number;
  current: number;
  pageSize: number;
  onPageChange: (page: number, pageSize: number) => void;
  scrollX?: number;
  className?: string;
};

function DataTable<T extends Record<string, unknown>>(props: DataTableProps<T>) {
  return (
    <ProTable<T>
      className={props.className}
      rowKey={props.rowKey}
      loading={props.loading}
      dataSource={props.dataSource}
      columns={props.columns}
      search={false}
      options={false}
      cardBordered
      cardProps={{ bodyStyle: { padding: 0 } }}
      pagination={{
        current: props.current,
        pageSize: props.pageSize,
        total: props.total,
        showSizeChanger: true,
        showTotal: (t, range) => `${range[0]}-${range[1]} / ${t}`,
        onChange: props.onPageChange,
      }}
      tableLayout="fixed"
      scroll={props.scrollX ? { x: props.scrollX } : undefined}
    />
  );
}

function DetailLinkButton({ onClick, label = '详情' }: { onClick: () => void; label?: string }) {
  return (
    <Button type="link" size="small" icon={<ArrowRightOutlined />} onClick={onClick} className="inline-link">
      {label}
    </Button>
  );
}

function AdapterTag({ ready }: { ready: boolean }) {
  return ready ? <Tag color="green">已开发</Tag> : <Tag>待开发</Tag>;
}

function GenerationTag({ status }: { status: string }) {
  const color = status === 'merged'
    ? 'green'
    : status === 'failed'
      ? 'red'
      : status === 'pending'
        ? 'default'
        : 'gold';
  return <Tag color={color}>{status}</Tag>;
}

type AdapterFilter = 'all' | 'ready' | 'pending';
type GenerationFilter = 'all' | 'pending' | 'claimed' | 'drafting' | 'merged' | 'failed';

type TasksApiResponse = {
  items: Task[];
  total: number;
  page: number;
  page_size: number;
};

function TasksPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [total, setTotal] = useState(0);
  const [pageInfo, setPageInfo] = useState({ current: 1, pageSize: 10 });
  const [loading, setLoading] = useState(false);
  const [adapterFilter, setAdapterFilter] = useState<AdapterFilter>('all');
  const [generationFilter, setGenerationFilter] = useState<GenerationFilter>('all');

  // 顶部汇总用单独 query 拿（不带 filter 的 page=1，page_size=1 取 total + facets）
  const [overview, setOverview] = useState<{ total: number; ready: number; merged: number }>({ total: 0, ready: 0, merged: 0 });

  const loadOverview = async () => {
    const [allRes, readyRes, mergedRes] = await Promise.all([
      api<TasksApiResponse>('/api/tasks?page=1&page_size=1'),
      api<TasksApiResponse>('/api/tasks?page=1&page_size=1&adapter=ready'),
      api<TasksApiResponse>('/api/tasks?page=1&page_size=1&generation_status=merged'),
    ]);
    setOverview({
      total: allRes.total,
      ready: readyRes.total,
      merged: mergedRes.total,
    });
  };

  const load = async (page = pageInfo.current, pageSize = pageInfo.pageSize) => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        page: String(page),
        page_size: String(pageSize),
      });
      if (adapterFilter !== 'all') params.set('adapter', adapterFilter);
      if (generationFilter !== 'all') params.set('generation_status', generationFilter);
      const data = await api<TasksApiResponse>(`/api/tasks?${params}`);
      setTasks(data.items);
      setTotal(data.total);
      setPageInfo({ current: page, pageSize });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadOverview();
  }, []);

  useEffect(() => {
    void load(1, pageInfo.pageSize);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [adapterFilter, generationFilter]);

  return (
    <PageContainer
      title="采集任务"
      subTitle="烯牛采集平台 · Source 任务与 URL frontier"
      extra={
        <Button
          icon={<ReloadOutlined />}
          onClick={() => {
            void loadOverview();
            void load(pageInfo.current, pageInfo.pageSize);
          }}
        >
          刷新
        </Button>
      }
    >
      <div className="summary-bar">
        <div><span>任务总数</span><strong>{overview.total}</strong></div>
        <div><span>Adapter 已开发</span><strong>{overview.ready} / {overview.total}</strong></div>
        <div><span>Codegen 已 merged</span><strong>{overview.merged}</strong></div>
        <div><span>当前筛选匹配</span><strong>{total}</strong></div>
      </div>
      <Flex gap={16} wrap="wrap" align="center" className="filter-bar">
        <Space size={8}>
          <Typography.Text type="secondary">Adapter</Typography.Text>
          <Segmented<AdapterFilter>
            value={adapterFilter}
            onChange={setAdapterFilter}
            options={[
              { label: '全部', value: 'all' },
              { label: `已开发 ${overview.ready}`, value: 'ready' },
              { label: `待开发 ${overview.total - overview.ready}`, value: 'pending' },
            ]}
          />
        </Space>
        <Space size={8}>
          <Typography.Text type="secondary">Codegen</Typography.Text>
          <Select<GenerationFilter>
            value={generationFilter}
            onChange={setGenerationFilter}
            style={{ minWidth: 140 }}
            options={[
              { label: '全部状态', value: 'all' },
              { label: 'pending', value: 'pending' },
              { label: 'claimed', value: 'claimed' },
              { label: 'drafting', value: 'drafting' },
              { label: 'merged', value: 'merged' },
              { label: 'failed', value: 'failed' },
            ]}
          />
        </Space>
        {(adapterFilter !== 'all' || generationFilter !== 'all') && (
          <Button
            size="small"
            type="link"
            onClick={() => {
              setAdapterFilter('all');
              setGenerationFilter('all');
            }}
          >
            清除筛选
          </Button>
        )}
      </Flex>
      <DataTable<Task>
        className="tasks-table"
        rowKey="task_id"
        loading={loading}
        dataSource={tasks}
        total={total}
        current={pageInfo.current}
        pageSize={pageInfo.pageSize}
        onPageChange={(page, pageSize) => void load(page, pageSize)}
        scrollX={1140}
        columns={[
          {
            title: 'Task',
            dataIndex: 'task_id',
            width: 154,
            render: (_, row) => (
              <Space direction="vertical" size={2} className="task-id-cell">
                <Button
                  type="link"
                  className="inline-link strong-link"
                  onClick={() => navigate(`/tasks/${row.task_id}`)}
                >
                  #{row.task_id}
                </Button>
                <Typography.Text type="secondary" className="cell-sub">
                  {row.created_at?.slice(0, 10)}
                </Typography.Text>
              </Space>
            ),
          },
          {
            title: 'Source',
            dataIndex: 'host',
            ellipsis: true,
            render: (_, row) => (
              <Space direction="vertical" size={2} className="source-cell">
                <Typography.Text strong>{row.host}</Typography.Text>
                <Typography.Text type="secondary" className="mono cell-sub" ellipsis>
                  {compactUrl(row.site_url)}
                </Typography.Text>
              </Space>
            ),
          },
          {
            title: 'Context',
            dataIndex: 'business_context',
            width: 138,
            render: (_, row) => (
              <Space direction="vertical" size={2}>
                <Typography.Text>{row.business_context}</Typography.Text>
                <Typography.Text type="secondary" className="cell-sub">
                  {row.data_kind} / {row.crawl_mode}
                </Typography.Text>
              </Space>
            ),
          },
          {
            title: 'Adapter',
            dataIndex: 'adapter_ready',
            width: 100,
            render: (_, row) => row.adapter_ready
              ? <Tag color="green">已开发</Tag>
              : <Tag>待开发</Tag>,
          },
          {
            title: 'Codegen',
            dataIndex: 'generation_status',
            width: 116,
            render: (_, row) => {
              const color = row.generation_status === 'merged'
                ? 'green'
                : row.generation_status === 'failed'
                  ? 'red'
                  : row.generation_status === 'pending'
                    ? 'default'
                    : 'gold';
              return <Tag color={color}>{row.generation_status}</Tag>;
            },
          },
          {
            title: 'Status',
            dataIndex: 'status',
            width: 116,
            render: (_, row) => <StatusTag value={row.status} />,
          },
          {
            title: 'Volume',
            width: 210,
            render: (_, row) => (
              <div className="metric-strip">
                <MetricCell label="URLs" value={row.url_count} />
                <MetricCell label="Fetch" value={row.fetch_count} />
                <MetricCell label="Raw" value={row.raw_count} />
              </div>
            ),
          },
          {
            title: 'Created by',
            dataIndex: 'created_by',
            width: 140,
            ellipsis: true,
          },
          {
            title: '操作',
            width: 96,
            fixed: 'right',
            render: (_, row) => (
              <Button
                type="link"
                size="small"
                icon={<ArrowRightOutlined />}
                onClick={() => navigate(`/tasks/${row.task_id}`)}
              >
                详情
              </Button>
            ),
          },
        ]}
      />
    </PageContainer>
  );
}

function TaskDetailPage({ taskId }: { taskId: number }) {
  const [detail, setDetail] = useState<{
    task: Task;
    progress: Record<string, number>;
    depth_summary: DepthSummary;
    fetched_depth_summary: DepthSummary;
    jump_depth_summary: DepthSummary;
    url_total: number;
    fetched_total: number;
    jump_total: number;
  } | null>(null);
  const [urlItems, setUrlItems] = useState<UrlRecord[]>([]);
  const [urlTotal, setUrlTotal] = useState(0);
  const [urlLoading, setUrlLoading] = useState(false);
  const [activeUrlTab, setActiveUrlTab] = useState<UrlTabKey>('all');
  const [urlPageInfo, setUrlPageInfo] = useState({ current: 1, pageSize: 10 });

  const loadDetail = async () => {
    const data = await api<NonNullable<typeof detail>>(`/api/tasks/${taskId}`);
    setDetail(data);
  };

  const loadUrls = async (
    current = 1,
    pageSize = 10,
    kind: UrlTabKey = activeUrlTab,
  ) => {
    setUrlLoading(true);
    try {
      const data = await api<{ items: UrlRecord[]; total: number }>(
        `/api/tasks/${taskId}/urls?kind=${kind}&limit=${pageSize}&offset=${(current - 1) * pageSize}`,
      );
      setUrlItems(data.items);
      setUrlTotal(data.total);
      setUrlPageInfo({ current, pageSize });
    } finally {
      setUrlLoading(false);
    }
  };

  useEffect(() => {
    void loadDetail();
  }, [taskId]);

  useEffect(() => {
    void loadUrls(1, 10, activeUrlTab);
  }, [taskId, activeUrlTab]);

  if (!detail) {
    return <PageContainer title={`Task #${taskId}`}><ProCard loading /></PageContainer>;
  }

  const { task, progress, depth_summary: depthSummary } = detail;
  const collectedTotal = progress.raw || 0;
  const uncollectedTotal = Math.max(detail.url_total - collectedTotal, 0);
  const renderUrl = (row: UrlRecord) => (
    <Space direction="vertical" size={3} className="url-cell">
      {row.raw_title ? (
        <Button
          type="link"
          className="inline-link url-title-link"
          onClick={() => navigate(`/tasks/${taskId}/items/${row.raw_id}`)}
        >
          {row.raw_title}
        </Button>
      ) : (
        <Typography.Text strong>未入库 URL</Typography.Text>
      )}
      <Typography.Text className="mono url-path" type="secondary" copyable={{ text: row.url }}>
        {compactUrl(row.url)}
      </Typography.Text>
      <Typography.Text type="secondary" className="mono cell-sub">
        fp {row.url_fp}
      </Typography.Text>
    </Space>
  );
  const renderContent = (row: UrlRecord) => {
    if (row.raw_id) {
      return (
        <Button
          icon={<ArrowRightOutlined />}
          size="small"
          onClick={() => navigate(`/tasks/${taskId}/items/${row.raw_id}`)}
        >
          详情
        </Button>
      );
    }
    if (row.status_code || row.error_kind) {
      return <Typography.Text type="secondary">已抓取，未生成采集内容</Typography.Text>;
    }
    return <Typography.Text type="secondary">未采集</Typography.Text>;
  };

  const hasData = detail.url_total > 0;

  const generationStatus = (task as Task & { generation_status?: string }).generation_status || 'pending';
  const adapterReady = Boolean((task as Task & { adapter_ready?: boolean }).adapter_ready);
  const generationColor = generationStatus === 'merged'
    ? 'green'
    : generationStatus === 'failed'
      ? 'red'
      : generationStatus === 'pending'
        ? 'default'
        : 'gold';

  return (
    <PageContainer
      title={task.host}
      subTitle={`Task #${task.task_id} · ${task.business_context} · ${task.data_kind} · ${task.crawl_mode}`}
      extra={
        <Space size={8}>
          <Tag color={adapterReady ? 'green' : 'default'}>
            Adapter {adapterReady ? '已开发' : '待开发'}
          </Tag>
          <Tag color={generationColor}>Codegen {generationStatus}</Tag>
          <StatusTag value={task.status} />
          <Button onClick={() => navigate('/tasks')}>返回任务</Button>
        </Space>
      }
    >
      <ProCard
        bordered
        className="compact-card"
        bodyStyle={{ padding: 0 }}
      >
        <div className="stat-strip">
          <div className="inline-stat"><span>URL records</span><strong>{detail.url_total}</strong></div>
          <div className="inline-stat"><span>已采集</span><strong>{collectedTotal}</strong></div>
          <div className="inline-stat"><span>未采集</span><strong>{uncollectedTotal}</strong></div>
          <div className="inline-stat inline-stat-wide"><span>Site URL</span>
            <Typography.Text copyable={{ text: task.site_url }} className="mono">
              {compactUrl(task.site_url)}
            </Typography.Text>
          </div>
          <div className="inline-stat"><span>Scope</span><strong>{task.scope_mode}</strong></div>
          <div className="inline-stat"><span>RPS</span><strong>{task.politeness_rps}</strong></div>
        </div>
      </ProCard>

      {!hasData && (
        <ProCard bordered className="compact-card" bodyStyle={{ padding: '40px 0' }}>
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={
              <Space direction="vertical" align="center" size={4}>
                <Typography.Text>本任务尚未发起采集</Typography.Text>
                <Typography.Text type="secondary">
                  scheduler claim 任务后会写入 URL frontier，此处自动展示进度。
                </Typography.Text>
              </Space>
            }
          />
        </ProCard>
      )}

      {hasData && (
      <ProCard
        title="URL 列表"
        subTitle={
          <Space size={10}>
            {depthSummary.map((item) => (
              <Typography.Text type="secondary" key={item.depth} className="cell-sub">
                depth {item.depth}: {item.url_count}
              </Typography.Text>
            ))}
          </Space>
        }
        bodyStyle={{ padding: '8px 12px 4px' }}
        className="url-sections"
      >
        <Tabs
          activeKey={activeUrlTab}
          onChange={(key) => setActiveUrlTab(key as UrlTabKey)}
          items={[
            { key: 'all', label: `全部 ${detail.url_total}` },
            { key: 'collected', label: `已采集 ${collectedTotal}` },
            { key: 'uncollected', label: `未采集 ${uncollectedTotal}` },
          ]}
        />
        <DataTable<UrlRecord>
          className="url-table"
          rowKey="url_fp"
          loading={urlLoading}
          dataSource={urlItems}
          total={urlTotal}
          current={urlPageInfo.current}
          pageSize={urlPageInfo.pageSize}
          onPageChange={(page, pageSize) => void loadUrls(page, pageSize)}
          scrollX={1120}
          columns={[
            { title: 'Depth', dataIndex: 'depth', width: 76 },
            {
              title: 'Content / URL',
              dataIndex: 'url',
              ellipsis: true,
              render: (_: unknown, row: UrlRecord) => renderUrl(row),
            },
            { title: 'State', dataIndex: 'frontier_state', width: 104,
              render: (_: unknown, row: UrlRecord) => <StatusTag value={row.frontier_state} /> },
            { title: 'Source', dataIndex: 'discovery_source', width: 132, ellipsis: true },
            {
              title: 'Fetch',
              width: 116,
              render: (_: unknown, row: UrlRecord) => row.status_code
                ? <Tag icon={<CheckCircleOutlined />} color="green">HTTP {row.status_code}</Tag>
                : (row.error_kind || '—'),
            },
            {
              title: 'Action',
              width: 112,
              render: (_: unknown, row: UrlRecord) => renderContent(row),
            },
          ]}
        />
      </ProCard>
      )}
    </PageContainer>
  );
}

function TaskItemPage({ taskId, itemId }: { taskId: number; itemId: number }) {
  const [detail, setDetail] = useState<{ task: Task; item: RawItem } | null>(null);

  useEffect(() => {
    setDetail(null);
    void api<{ task: Task; item: RawItem }>(`/api/tasks/${taskId}/items/${itemId}`)
      .then((data) => setDetail(data));
  }, [taskId, itemId]);

  if (!detail) {
    return <PageContainer title={`Raw #${itemId}`}><ProCard loading /></PageContainer>;
  }

  const { task, item } = detail;
  const metadataEntries = Object.entries(item.source_metadata || {});
  const childLinks = item.child_links || [];
  const childLinkTypeLabel = (row: ChildLink) => (
    row.link_type === 'attachment'
      ? '附件'
      : row.link_type === 'interpret'
        ? '解读'
        : '链接'
  );
  const childLinkTypeColor = (row: ChildLink) => (row.link_type === 'attachment' ? 'orange' : 'blue');

  const attachmentLinks = childLinks;

  return (
    <PageContainer
      title={item.title}
      subTitle={
        <Typography.Text type="secondary" className="mono">
          {item.host} · Task #{task.task_id} · Raw #{item.id}
        </Typography.Text>
      }
      extra={
        <Button
          icon={<ArrowRightOutlined rotate={180} />}
          onClick={() => navigate(`/tasks/${taskId}`)}
        >
          返回 Source
        </Button>
      }
    >
      <div className="item-layout">
        <ProCard
          title="采集内容"
          headerBordered
          className="section-card item-card"
        >
          {metadataEntries.length > 0 && (
            <div className="capture-fields">
              {metadataEntries.map(([key, value]) => (
                <div className="capture-field" key={key}>
                  <span className="capture-field-label">{key}</span>
                  <span className="capture-field-value">{String(value)}</span>
                </div>
              ))}
            </div>
          )}
          {item.body_text
            ? <pre className="body-pre">{item.body_text}</pre>
            : (
              <div style={{ padding: 16 }}>
                <Typography.Text type="secondary">暂无正文内容。</Typography.Text>
              </div>
            )
          }
        </ProCard>

        <ProCard
          title="入库信息"
          headerBordered
          className="section-card item-card"
        >
          <div className="storage-row">
            <span className="storage-label">Task</span>
            <span className="storage-value mono">#{task.task_id}</span>
          </div>
          <div className="storage-row">
            <span className="storage-label">Raw ID</span>
            <span className="storage-value mono">#{item.id}</span>
          </div>
          <div className="storage-row">
            <span className="storage-label">Host</span>
            <span className="storage-value mono">{item.host}</span>
          </div>
          <div className="storage-row">
            <span className="storage-label">源 URL</span>
            <span className="storage-value">
              <Typography.Text copyable={{ text: item.url }} className="mono">
                {compactUrl(item.url)}
              </Typography.Text>
            </span>
          </div>
          <div className="storage-row">
            <span className="storage-label">Raw blob</span>
            <span className="storage-value">
              <Typography.Text copyable={{ text: item.raw_blob_uri }} className="mono">
                {item.raw_blob_uri}
              </Typography.Text>
            </span>
          </div>
          <div className="storage-row">
            <span className="storage-label">Created</span>
            <span className="storage-value mono">{item.created_at}</span>
          </div>
          <div className="storage-row">
            <span className="storage-label">Attachments</span>
            <span className="storage-value">{attachmentLinks.length}</span>
          </div>
          {attachmentLinks.map((row) => (
            <div key={row.url} className="storage-link-row">
              <Tag color={childLinkTypeColor(row)}>{childLinkTypeLabel(row)}</Tag>
              <Typography.Link
                href={row.url}
                target="_blank"
                rel="noreferrer"
                className="child-title"
              >
                {row.filename || compactUrl(row.url)}
              </Typography.Link>
              <Typography.Text className="mono child-sub" copyable={{ text: row.url }}>
                {compactUrl(row.url)}
              </Typography.Text>
            </div>
          ))}
        </ProCard>
      </div>
    </PageContainer>
  );
}

function AdaptersPage() {
  const [items, setItems] = useState<Adapter[]>([]);
  const [loading, setLoading] = useState(false);
  const [pageInfo, setPageInfo] = useState({ current: 1, pageSize: 20 });

  const load = async () => {
    setLoading(true);
    try {
      const data = await api<{ items: Adapter[] }>('/api/adapters');
      setItems(data.items);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, []);

  const summary = useMemo(() => {
    const ctxCount = new Set(items.map((it) => it.business_context)).size;
    const latest = items.reduce<string>(
      (acc, it) => (it.last_verified_at > acc ? it.last_verified_at : acc),
      '',
    );
    const renderModes = new Set(items.map((it) => it.render_mode));
    return {
      total: items.length,
      contexts: ctxCount,
      latest: latest || '—',
      renderModes: Array.from(renderModes).join(' / ') || '—',
    };
  }, [items]);

  const pageItems = useMemo(() => {
    const start = (pageInfo.current - 1) * pageInfo.pageSize;
    return items.slice(start, start + pageInfo.pageSize);
  }, [items, pageInfo]);

  return (
    <PageContainer
      title="Adapters"
      subTitle="已注册站点适配器"
      extra={<Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>}
    >
      <div className="summary-bar">
        <div><span>Adapter 总数</span><strong>{summary.total}</strong></div>
        <div><span>业务域数</span><strong>{summary.contexts}</strong></div>
        <div><span>渲染模式</span><strong>{summary.renderModes}</strong></div>
        <div><span>最近校验</span><strong>{summary.latest}</strong></div>
      </div>
      <DataTable<Adapter>
        rowKey="module_path"
        loading={loading}
        dataSource={pageItems}
        total={items.length}
        current={pageInfo.current}
        pageSize={pageInfo.pageSize}
        onPageChange={(current, pageSize) => setPageInfo({ current, pageSize })}
        scrollX={1100}
        columns={[
          {
            title: 'Host',
            dataIndex: 'host',
            render: (_, row) => (
              <div className="cell-stack">
                <Typography.Text strong>{row.host}</Typography.Text>
                <Typography.Text type="secondary" className="mono cell-sub">
                  {row.module_path}
                </Typography.Text>
              </div>
            ),
          },
          { title: 'Context', dataIndex: 'business_context', width: 150 },
          { title: 'Kind', dataIndex: 'data_kind', width: 120 },
          {
            title: 'Schema',
            dataIndex: 'schema_version',
            width: 100,
            render: (_, row) => `v${row.schema_version}`,
          },
          {
            title: 'Render',
            dataIndex: 'render_mode',
            width: 120,
            render: (_, row) => <Tag color={row.render_mode === 'direct' ? 'blue' : 'gold'}>{row.render_mode}</Tag>,
          },
          { title: 'Verified', dataIndex: 'last_verified_at', width: 140 },
        ]}
      />
    </PageContainer>
  );
}

type MonitorState = {
  taskTotal: number;
  adapterReady: number;
  codegenMerged: number;
  codegenFailed: number;
  rawTotal: number;
  contextDist: Record<string, number>;
  generationDist: Record<string, number>;
};

function MonitorPage() {
  const [state, setState] = useState<MonitorState | null>(null);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const [allRes, mergedRes, failedRes] = await Promise.all([
        api<TasksApiResponse>('/api/tasks?page=1&page_size=200'),
        api<TasksApiResponse>('/api/tasks?page=1&page_size=1&generation_status=merged'),
        api<TasksApiResponse>('/api/tasks?page=1&page_size=1&generation_status=failed'),
      ]);
      const items = allRes.items;
      const contextDist: Record<string, number> = {};
      const generationDist: Record<string, number> = {};
      let raw = 0;
      let ready = 0;
      for (const it of items) {
        contextDist[it.business_context] = (contextDist[it.business_context] || 0) + 1;
        generationDist[it.generation_status] = (generationDist[it.generation_status] || 0) + 1;
        raw += it.raw_count || 0;
        if (it.adapter_ready) ready += 1;
      }
      setState({
        taskTotal: allRes.total,
        adapterReady: ready,
        codegenMerged: mergedRes.total,
        codegenFailed: failedRes.total,
        rawTotal: raw,
        contextDist,
        generationDist,
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, []);

  if (!state) {
    return (
      <PageContainer title="监控" subTitle="任务与 source 运行态">
        <ProCard loading={loading || true} className="section-card" />
      </PageContainer>
    );
  }

  const distMax = (dist: Record<string, number>) =>
    Math.max(1, ...Object.values(dist));

  const renderDist = (dist: Record<string, number>) => {
    const max = distMax(dist);
    const entries = Object.entries(dist).sort((a, b) => b[1] - a[1]);
    return (
      <div className="dist-list">
        {entries.map(([k, v]) => {
          const pct = Math.round((v / max) * 100);
          return (
            <div key={k} className="dist-row">
              <span>{k}</span>
              <div
                className="dist-bar"
                style={{ backgroundSize: `${pct}% 100%` }}
              />
              <span className="dist-count">{v}</span>
            </div>
          );
        })}
      </div>
    );
  };

  return (
    <PageContainer
      title="监控"
      subTitle="任务、adapter、codegen 与采集量总览"
      extra={<Button icon={<ReloadOutlined />} onClick={load} loading={loading}>刷新</Button>}
    >
      <div className="dashboard-grid" style={{ marginBottom: 12 }}>
        <div className="dashboard-tile">
          <h4>任务总数</h4>
          <div className="tile-value">{state.taskTotal}</div>
          <div className="tile-sub">crawl_task 表所有 task</div>
        </div>
        <div className="dashboard-tile">
          <h4>Adapter 已开发</h4>
          <div className="tile-value">{state.adapterReady} / {state.taskTotal}</div>
          <div className="tile-sub">adapter_registry 派生（filesystem 真值）</div>
        </div>
        <div className="dashboard-tile">
          <h4>Codegen merged</h4>
          <div className="tile-value">{state.codegenMerged}</div>
          <div className="tile-sub">crawl_task_generation.status = merged</div>
        </div>
        <div className="dashboard-tile">
          <h4>Codegen failed</h4>
          <div className="tile-value">{state.codegenFailed}</div>
          <div className="tile-sub">最近一次跑 wrapper gates 红</div>
        </div>
        <div className="dashboard-tile">
          <h4>Raw 入库总数</h4>
          <div className="tile-value">{state.rawTotal}</div>
          <div className="tile-sub">crawl_raw 总记录</div>
        </div>
      </div>

      <ProCard
        title="业务域分布"
        headerBordered
        className="section-card"
      >
        {renderDist(state.contextDist)}
      </ProCard>

      <ProCard
        title="Codegen 状态分布"
        headerBordered
        className="section-card"
      >
        {renderDist(state.generationDist)}
      </ProCard>
    </PageContainer>
  );
}

function Shell() {
  const [route, setRoute] = useState<RouteState>(parseRoute());

  useEffect(() => {
    const onPopState = () => setRoute(parseRoute());
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  const selectedKey = route.name === 'task' || route.name === 'item' ? '/tasks' : `/${route.name}`;
  return (
    <ProLayout
      title="烯牛采集平台"
      logo={<DatabaseOutlined />}
      layout="side"
      navTheme="light"
      contentWidth="Fluid"
      fixedHeader
      route={{
        path: '/',
        routes: [
          { path: '/tasks', name: '任务', icon: <AppstoreOutlined /> },
          { path: '/monitor', name: '监控', icon: <BarChartOutlined /> },
          { path: '/adapters', name: 'Adapters', icon: <LinkOutlined /> },
        ],
      }}
      location={{ pathname: selectedKey }}
      menuItemRender={(item, dom) => (
        <a onClick={() => navigate(item.path || '/tasks')}>{dom}</a>
      )}
    >
      {route.name === 'task' && <TaskDetailPage taskId={route.taskId} />}
      {route.name === 'item' && <TaskItemPage taskId={route.taskId} itemId={route.itemId} />}
      {route.name === 'tasks' && <TasksPage />}
      {route.name === 'adapters' && <AdaptersPage />}
      {route.name === 'monitor' && <MonitorPage />}
    </ProLayout>
  );
}

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <ConfigProvider
      theme={{
        algorithm: theme.defaultAlgorithm,
        token: {
          colorPrimary: '#3154d4',
          borderRadius: 8,
          fontFamily: '-apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", "Helvetica Neue", Arial, sans-serif',
        },
      }}
    >
      <AntApp>
        <Shell />
      </AntApp>
    </ConfigProvider>
  </React.StrictMode>,
);
