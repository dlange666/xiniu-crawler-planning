import React, { useEffect, useMemo, useState } from 'react';
import ReactDOM from 'react-dom/client';
import {
  App as AntApp,
  Button,
  ConfigProvider,
  Descriptions,
  Empty,
  Flex,
  Select,
  Space,
  Tag,
  Typography,
  theme,
} from 'antd';
import {
  AppstoreOutlined,
  BarChartOutlined,
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
  raw_count: number;
  url_count: number;
  fetch_count: number;
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

type Adapter = {
  business_context: string;
  host: string;
  data_kind: string;
  schema_version: number;
  render_mode: string;
  last_verified_at: string;
  module_path: string;
};

type RouteState =
  | { name: 'tasks' }
  | { name: 'task'; taskId: number }
  | { name: 'adapters' }
  | { name: 'monitor' };

async function api<T>(path: string): Promise<T> {
  const response = await fetch(path, { headers: { 'X-Requested-With': 'webui' } });
  if (!response.ok) throw new Error(`${path} ${response.status}`);
  return response.json() as Promise<T>;
}

function parseRoute(): RouteState {
  const path = window.location.pathname.replace(/^\/ui/, '') || '/tasks';
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
        <div><span>URL records</span><strong>{totals.urls}</strong></div>
        <div><span>Fetch records</span><strong>{totals.fetches}</strong></div>
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
            width: 90,
            render: (_, row) => <Button type="link" onClick={() => navigate(`/tasks/${row.task_id}`)}>#{row.task_id}</Button>,
          },
          { title: 'Host', dataIndex: 'host', ellipsis: true },
          { title: 'Context', dataIndex: 'business_context', width: 140 },
          { title: 'Status', dataIndex: 'status', width: 130, render: (_, row) => <StatusTag value={row.status} /> },
          { title: 'URLs', dataIndex: 'url_count', width: 110 },
          { title: 'Raw', dataIndex: 'raw_count', width: 90 },
          { title: 'Created by', dataIndex: 'created_by', width: 160 },
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
  const [fetchedUrls, setFetchedUrls] = useState<UrlRecord[]>([]);
  const [jumpUrls, setJumpUrls] = useState<UrlRecord[]>([]);
  const [fetchedTotal, setFetchedTotal] = useState(0);
  const [jumpTotal, setJumpTotal] = useState(0);
  const [fetchedLoading, setFetchedLoading] = useState(false);
  const [jumpLoading, setJumpLoading] = useState(false);
  const [jumpDepth, setJumpDepth] = useState<number | 'all'>('all');

  const loadDetail = async () => {
    const data = await api<NonNullable<typeof detail>>(`/api/tasks/${taskId}`);
    setDetail(data);
    const firstDeepJump = data.jump_depth_summary.find((item) => item.depth > 0);
    if (firstDeepJump) setJumpDepth(firstDeepJump.depth);
  };

  const loadFetchedUrls = async (current = 1, pageSize = 10) => {
    setFetchedLoading(true);
    try {
      const data = await api<{ items: UrlRecord[]; total: number }>(
        `/api/tasks/${taskId}/urls?kind=fetched&limit=${pageSize}&offset=${(current - 1) * pageSize}`,
      );
      setFetchedUrls(data.items);
      setFetchedTotal(data.total);
    } finally {
      setFetchedLoading(false);
    }
  };

  const loadJumpUrls = async (
    current = 1,
    pageSize = 10,
    depth: number | 'all' = jumpDepth,
  ) => {
    setJumpLoading(true);
    try {
      const params = new URLSearchParams({
        kind: 'jump',
        limit: String(pageSize),
        offset: String((current - 1) * pageSize),
      });
      if (depth !== 'all') params.set('depth', String(depth));
      const data = await api<{ items: UrlRecord[]; total: number }>(
        `/api/tasks/${taskId}/urls?${params.toString()}`,
      );
      setJumpUrls(data.items);
      setJumpTotal(data.total);
    } finally {
      setJumpLoading(false);
    }
  };

  useEffect(() => {
    void loadDetail();
    void loadFetchedUrls();
  }, [taskId]);

  useEffect(() => {
    void loadJumpUrls(1, 10, jumpDepth);
  }, [taskId, jumpDepth]);

  if (!detail) {
    return <PageContainer title={`Task #${taskId}`}><ProCard loading /></PageContainer>;
  }

  const { task, progress, depth_summary: depthSummary } = detail;
  return (
    <PageContainer
      title={task.host}
      subTitle={`Task #${task.task_id} · ${task.business_context}`}
      extra={<Button onClick={() => navigate('/tasks')}>返回任务</Button>}
    >
      <div className="summary-bar dense">
        <div><span>状态</span><strong>{task.status}</strong></div>
        <div><span>URL records</span><strong>{detail.url_total}</strong></div>
        <div><span>已抓取链接</span><strong>{detail.fetched_total}</strong></div>
        <div><span>跳转链接</span><strong>{detail.jump_total}</strong></div>
      </div>

      <ProCard split="vertical" gutter={12} className="compact-card" bodyStyle={{ padding: 0 }}>
        <ProCard title="Source 参数" colSpan="42%">
          <Descriptions column={1} size="small">
            <Descriptions.Item label="Site URL">{task.site_url}</Descriptions.Item>
            <Descriptions.Item label="Data kind">{task.data_kind}</Descriptions.Item>
            <Descriptions.Item label="Crawl mode">{task.crawl_mode}</Descriptions.Item>
            <Descriptions.Item label="Scope">{task.scope_mode}</Descriptions.Item>
            <Descriptions.Item label="RPS">{task.politeness_rps}</Descriptions.Item>
          </Descriptions>
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

      <ProCard split="horizontal" gutter={10} bodyStyle={{ padding: 0 }} className="url-sections">
        <ProCard
          title="已抓取链接"
          subTitle="fetch_record / crawl_raw 结果"
          extra={<Typography.Text type="secondary">API: /api/tasks/{task.task_id}/urls?kind=fetched</Typography.Text>}
        >
          <ProTable<UrlRecord>
            className="url-table"
            rowKey="url_fp"
            loading={fetchedLoading}
            dataSource={fetchedUrls}
            search={false}
            options={false}
            cardBordered={false}
            cardProps={{ bodyStyle: { padding: 0 } }}
            pagination={{
              total: fetchedTotal,
              pageSize: 10,
              showSizeChanger: true,
              showTotal: (total, range) => `${range[0]}-${range[1]} / ${total}`,
              onChange: (page, pageSize) => void loadFetchedUrls(page, pageSize),
            }}
            columns={[
              { title: 'Depth', dataIndex: 'depth', width: 74 },
              {
                title: '抓取链接',
                dataIndex: 'url',
                ellipsis: true,
                render: (_, row) => (
                  <Space direction="vertical" size={0}>
                    <Typography.Link href={row.url} target="_blank">{row.url}</Typography.Link>
                    <Typography.Text type="secondary" className="mono">{row.url_fp}</Typography.Text>
                  </Space>
                ),
              },
              { title: 'State', dataIndex: 'frontier_state', width: 110, render: (_, row) => <StatusTag value={row.frontier_state} /> },
              {
                title: 'Fetch',
                width: 120,
                render: (_, row) => row.status_code ? `HTTP ${row.status_code}` : (row.error_kind || '—'),
              },
              {
                title: '内容',
                width: 260,
                render: (_, row) => row.raw_id
                  ? (
                    <Space direction="vertical" size={0}>
                      <Typography.Text>{row.raw_title}</Typography.Text>
                      <Typography.Text type="secondary" ellipsis>{row.raw_excerpt}</Typography.Text>
                    </Space>
                  )
                  : <Typography.Text type="secondary">已抓取，暂无 crawl_raw 内容</Typography.Text>,
              },
            ]}
          />
        </ProCard>

        <ProCard
          title="跳转链接"
          subTitle="已发现，等待后续抓取"
          extra={(
            <Space>
              <Typography.Text type="secondary">Depth</Typography.Text>
              <Select
                size="small"
                value={jumpDepth}
                style={{ width: 120 }}
                onChange={(value) => setJumpDepth(value)}
                options={[
                  { label: '全部', value: 'all' },
                  ...detail.jump_depth_summary.map((item) => ({
                    label: `depth ${item.depth}`,
                    value: item.depth,
                  })),
                ]}
              />
            </Space>
          )}
        >
          <ProTable<UrlRecord>
            className="url-table"
            rowKey="url_fp"
            loading={jumpLoading}
            dataSource={jumpUrls}
            search={false}
            options={false}
            cardBordered={false}
            cardProps={{ bodyStyle: { padding: 0 } }}
            pagination={{
              total: jumpTotal,
              pageSize: 10,
              showSizeChanger: true,
              showTotal: (total, range) => `${range[0]}-${range[1]} / ${total}`,
              onChange: (page, pageSize) => void loadJumpUrls(page, pageSize),
            }}
            columns={[
              { title: 'Depth', dataIndex: 'depth', width: 74 },
              {
                title: '跳转链接',
                dataIndex: 'url',
                ellipsis: true,
                render: (_, row) => (
                  <Space direction="vertical" size={0}>
                    <Typography.Link href={row.url} target="_blank">{row.url}</Typography.Link>
                    <Typography.Text type="secondary" className="mono">{row.url_fp}</Typography.Text>
                  </Space>
                ),
              },
              { title: 'State', dataIndex: 'frontier_state', width: 110, render: (_, row) => <StatusTag value={row.frontier_state} /> },
              { title: 'Source', dataIndex: 'discovery_source', width: 140 },
              {
                title: 'Parent',
                dataIndex: 'parent_url_fp',
                width: 180,
                render: (_, row) => row.parent_url_fp
                  ? <Typography.Text type="secondary" className="mono">{row.parent_url_fp}</Typography.Text>
                  : <Typography.Text type="secondary">seed</Typography.Text>,
              },
            ]}
          />
        </ProCard>
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

  const selectedKey = route.name === 'task' ? '/tasks' : `/${route.name}`;
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
