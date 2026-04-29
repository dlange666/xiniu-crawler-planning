import React, { useEffect, useMemo, useState } from 'react';
import ReactDOM from 'react-dom/client';
import {
  App as AntApp,
  Button,
  ConfigProvider,
  Empty,
  Flex,
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

function TasksPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const data = await api<{ items: Task[] }>('/api/tasks');
      setTasks(data.items);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const totals = useMemo(() => ({
    tasks: tasks.length,
    adapterReady: tasks.filter((item) => item.adapter_ready).length,
    codegenMerged: tasks.filter((item) => item.generation_status === 'merged').length,
    codegenFailed: tasks.filter((item) => item.generation_status === 'failed').length,
    urls: tasks.reduce((sum, item) => sum + (item.url_count || 0), 0),
    raw: tasks.reduce((sum, item) => sum + (item.raw_count || 0), 0),
    fetches: tasks.reduce((sum, item) => sum + (item.fetch_count || 0), 0),
  }), [tasks]);

  return (
    <PageContainer
      title="采集任务"
      subTitle="烯牛采集平台 · Source 任务与 URL frontier"
      extra={<Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>}
    >
      <div className="summary-bar">
        <div><span>任务数</span><strong>{totals.tasks}</strong></div>
        <div><span>Adapter 已开发</span><strong>{totals.adapterReady} / {totals.tasks}</strong></div>
        <div><span>Codegen 已 merged</span><strong>{totals.codegenMerged}</strong></div>
        <div><span>URL records</span><strong>{totals.urls}</strong></div>
        <div><span>Raw items</span><strong>{totals.raw}</strong></div>
      </div>
      <ProTable<Task>
        className="tasks-table"
        rowKey="task_id"
        loading={loading}
        dataSource={tasks}
        search={false}
        options={false}
        pagination={tasks.length > 10 ? { pageSize: 10, showSizeChanger: false } : false}
        cardBordered
        cardProps={{ bodyStyle: { padding: 0 } }}
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
        tableLayout="fixed"
        scroll={{ x: 1140 }}
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

  return (
    <PageContainer
      title={task.host}
      subTitle={`Task #${task.task_id} · ${task.business_context}`}
      extra={<Button onClick={() => navigate('/tasks')}>返回任务</Button>}
    >
      <div className="summary-bar dense">
        <div><span>状态</span><strong>{task.status}</strong></div>
        <div><span>URL records</span><strong>{detail.url_total}</strong></div>
        <div><span>已采集</span><strong>{collectedTotal}</strong></div>
        <div><span>未采集</span><strong>{uncollectedTotal}</strong></div>
      </div>

      <ProCard split="vertical" gutter={12} className="compact-card" bodyStyle={{ padding: 0 }}>
        <ProCard title="Source 参数" colSpan="42%">
          <div className="field-grid">
            <div><span>Site URL</span><Typography.Text copyable className="mono">{compactUrl(task.site_url)}</Typography.Text></div>
            <div><span>Data kind</span><strong>{task.data_kind}</strong></div>
            <div><span>Crawl mode</span><strong>{task.crawl_mode}</strong></div>
            <div><span>Scope</span><strong>{task.scope_mode}</strong></div>
            <div><span>RPS</span><strong>{task.politeness_rps}</strong></div>
          </div>
        </ProCard>
        <ProCard title="Depth 分布">
          <Flex wrap="wrap" gap={8}>
            {depthSummary.map((item) => (
              <Tag className="depth-tag" color="blue" key={item.depth}>
                depth {item.depth}: {item.url_count}
              </Tag>
            ))}
          </Flex>
          <Space className="state-counts" size={14}>
            <Typography.Text type="secondary">pending {progress.pending || 0}</Typography.Text>
            <Typography.Text type="secondary">done {progress.done || 0}</Typography.Text>
            <Typography.Text type="secondary">raw {progress.raw || 0}</Typography.Text>
          </Space>
        </ProCard>
      </ProCard>

      <ProCard
        title="URL 列表"
        subTitle="通过 crawl_raw 是否存在区分采集状态"
        extra={<Typography.Text type="secondary">{`API: /api/tasks/${task.task_id}/urls?kind=${activeUrlTab}`}</Typography.Text>}
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
        <ProTable<UrlRecord>
          className="url-table"
          rowKey="url_fp"
          loading={urlLoading}
          dataSource={urlItems}
          search={false}
          options={false}
          cardBordered={false}
          cardProps={{ bodyStyle: { padding: 0 } }}
          pagination={{
            total: urlTotal,
            pageSize: 10,
            showSizeChanger: true,
            showTotal: (total, range) => `${range[0]}-${range[1]} / ${total}`,
            onChange: (page, pageSize) => void loadUrls(page, pageSize),
          }}
          columns={[
            { title: 'Depth', dataIndex: 'depth', width: 76 },
            {
              title: 'Content / URL',
              dataIndex: 'url',
              ellipsis: true,
              render: (_, row) => renderUrl(row),
            },
            { title: 'State', dataIndex: 'frontier_state', width: 104, render: (_, row) => <StatusTag value={row.frontier_state} /> },
            { title: 'Source', dataIndex: 'discovery_source', width: 132, ellipsis: true },
            {
              title: 'Fetch',
              width: 116,
              render: (_, row) => row.status_code
                ? <Tag icon={<CheckCircleOutlined />} color="green">HTTP {row.status_code}</Tag>
                : (row.error_kind || '—'),
            },
            {
              title: 'Action',
              width: 112,
              render: (_, row) => renderContent(row),
            },
          ]}
          tableLayout="fixed"
          scroll={{ x: 1120 }}
        />
      </ProCard>
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

  return (
    <PageContainer
      title={item.title}
      subTitle={`Task #${task.task_id} · Raw #${item.id} · ${item.host}`}
      extra={<Button onClick={() => navigate(`/tasks/${taskId}`)}>返回 Source</Button>}
    >
      <ProCard split="vertical" gutter={12} className="compact-card" bodyStyle={{ padding: 0 }}>
        <ProCard title="采集内容" colSpan="64%">
          <Typography.Paragraph className="body-preview">
            {item.body_text || '暂无正文内容。'}
          </Typography.Paragraph>
        </ProCard>
        <ProCard title="入库信息" className="storage-info-card">
          <div className="storage-info-list">
            <div className="storage-info-row">
              <div className="storage-info-label">源 URL</div>
              <div className="storage-info-value">
                <Typography.Text copyable={{ text: item.url }} className="mono breakable-value">
                  {compactUrl(item.url)}
                </Typography.Text>
              </div>
            </div>
            <div className="storage-info-row">
              <div className="storage-info-label">Raw blob</div>
              <div className="storage-info-value">
                <Typography.Text copyable className="mono breakable-value">
                  {item.raw_blob_uri}
                </Typography.Text>
              </div>
            </div>
            <div className="storage-info-row">
              <div className="storage-info-label">Created at</div>
              <div className="storage-info-value">{item.created_at}</div>
            </div>
            <div className="storage-info-row">
              <div className="storage-info-label">Attachments</div>
              <div className="storage-info-value">
                <Typography.Text>{item.attachments?.length || 0}</Typography.Text>
              </div>
            </div>
            {childLinks.map((row) => (
              <div className="storage-info-row child-link-row" key={row.url}>
                <div className="storage-info-label child-link-label">
                  <Tag color={childLinkTypeColor(row)}>{childLinkTypeLabel(row)}</Tag>
                </div>
                <div className="storage-info-value">
                  <Space direction="vertical" size={2} className="child-link-text">
                    <Typography.Link
                      href={row.url}
                      target="_blank"
                      rel="noreferrer"
                      strong={row.link_type === 'attachment'}
                      className="child-link-title"
                    >
                      {row.filename || compactUrl(row.url)}
                    </Typography.Link>
                    <Typography.Text type="secondary" copyable={{ text: row.url }} className="mono child-url">
                      {compactUrl(row.url)}
                    </Typography.Text>
                  </Space>
                </div>
              </div>
            ))}
          </div>
        </ProCard>
      </ProCard>

      <ProCard title="Source metadata" className="compact-card">
        {metadataEntries.length ? (
          <div className="metadata-grid">
            {metadataEntries.map(([key, value]) => (
              <div className="metadata-row" key={key}>
                <span>{key}</span>
                <strong>{String(value)}</strong>
              </div>
            ))}
          </div>
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无 source metadata" />
        )}
      </ProCard>

    </PageContainer>
  );
}

function AdaptersPage() {
  const [items, setItems] = useState<Adapter[]>([]);
  useEffect(() => {
    void api<{ items: Adapter[] }>('/api/adapters').then((data) => setItems(data.items));
  }, []);
  return (
    <PageContainer title="Adapters" subTitle="已注册站点适配器">
      <ProTable<Adapter>
        rowKey="module_path"
        dataSource={items}
        search={false}
        options={false}
        cardBordered
        cardProps={{ bodyStyle: { padding: 0 } }}
        columns={[
          { title: 'Host', dataIndex: 'host' },
          { title: 'Context', dataIndex: 'business_context', width: 150 },
          { title: 'Kind', dataIndex: 'data_kind', width: 120 },
          { title: 'Schema', dataIndex: 'schema_version', width: 100, render: (_, row) => `v${row.schema_version}` },
          { title: 'Render', dataIndex: 'render_mode', width: 120 },
          { title: 'Verified', dataIndex: 'last_verified_at', width: 140 },
        ]}
      />
    </PageContainer>
  );
}

function MonitorPage() {
  return (
    <PageContainer title="监控" subTitle="TD-013 前先展示任务与 source 运行态">
      <Empty description="metric_snapshot 尚未接入；请先在任务详情查看 URL frontier 与 fetch 状态。" />
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
