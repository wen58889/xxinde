import { Box, Button, IconButton, Tooltip, Select, MenuItem } from '@mui/material'
import SettingsIcon from '@mui/icons-material/Settings'
import AddIcon from '@mui/icons-material/Add'
import DeleteIcon from '@mui/icons-material/Delete'
import FolderOpenIcon from '@mui/icons-material/FolderOpen'
import DownloadIcon from '@mui/icons-material/Download'
import { useState, useEffect } from 'react'
import { useRuleStore } from '../../stores/ruleStore'
import { useLogStore } from '../../stores/logStore'
import { templatesApi, tasksApi } from '../../api/devices'
import { useDeviceStore } from '../../stores/deviceStore'
import { colors } from '../../theme'
import { rulesToYaml } from '../../utils/rulesYaml'

export default function ScriptToolbar() {
  const rules = useRuleStore((s) => s.rules)
  const addRule = useRuleStore((s) => s.addRule)
  const clearAll = useRuleStore((s) => s.clearAll)
  const loadRules = useRuleStore((s) => s.loadRules)
  const addLog = useLogStore((s) => s.addLog)
  const selectedDeviceId = useDeviceStore((s) => s.selectedDeviceId)

  const [templates, setTemplates] = useState<{ id: number; name: string; yaml_content: string }[]>([])
  const [selectedTplId, setSelectedTplId] = useState('')

  const refreshTemplates = () => {
    templatesApi.list()
      .then((list: any[]) => setTemplates(list))
      .catch(() => {})
  }

  useEffect(() => { refreshTemplates() }, [])

  const handleSave = async () => {
    try {
      await templatesApi.create({
        app_name: 'default',
        name: `flow_${Date.now()}`,
        yaml_content: JSON.stringify(rules),
      })
      addLog('流程已保存', 'success')
      refreshTemplates()
    } catch (e) {
      addLog(`保存失败: ${e}`, 'error')
    }
  }

  const handleLoadTemplate = (id: string) => {
    setSelectedTplId(id)
    const tpl = templates.find(t => t.id === Number(id))
    if (!tpl) return
    try {
      const parsed = JSON.parse(tpl.yaml_content)
      if (Array.isArray(parsed)) {
        loadRules(parsed)
        addLog(`已加载模板: ${tpl.name}`, 'success')
      } else {
        addLog('该模板为 YAML 格式，可直接运行但无法在编辑器中展示', 'warn')
      }
    } catch {
      addLog('模板格式不兼容', 'error')
    }
  }

  const handleRun = async () => {
    if (!selectedDeviceId) {
      addLog('请先选择设备', 'warn')
      return
    }
    try {
      const yaml = rulesToYaml(rules)
      const res = await tasksApi.runYaml(selectedDeviceId, yaml) as any
      addLog(`任务已提交 #${res.id}`, 'success')
    } catch (e: any) {
      const detail = e?.response?.data?.detail
      const msg = detail || (e instanceof Error ? e.message : String(e))
      addLog(`运行失败: ${msg}`, 'error')
    }
  }

  const handleStop = async () => {
    if (!selectedDeviceId) return
    try {
      await tasksApi.stop(selectedDeviceId)
      addLog('任务已停止', 'warn')
    } catch (e) {
      addLog(`停止失败: ${e}`, 'error')
    }
  }

  const handleExportYaml = () => {
    const yaml = rulesToYaml(rules)
    const blob = new Blob([yaml], { type: 'text/yaml' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `flow_${Date.now()}.yaml`
    a.click()
    URL.revokeObjectURL(url)
    addLog('已导出 YAML 文件', 'success')
  }

  return (
    <Box sx={{ display: 'flex', gap: 0.5, alignItems: 'center', flexWrap: 'wrap' }}>
      <Button size="small" variant="contained" onClick={handleSave}
        sx={{ bgcolor: colors.success, '&:hover': { bgcolor: '#4caf50' } }}>
        保存
      </Button>
      <Select
        size="small"
        value={selectedTplId}
        onChange={(e) => handleLoadTemplate(e.target.value)}
        displayEmpty
        renderValue={(v) => v ? templates.find(t => t.id === Number(v))?.name ?? '加载模板' : '加载模板'}
        startAdornment={<FolderOpenIcon sx={{ fontSize: 14, mr: 0.5, color: '#aaa' }} />}
        sx={{ height: 30, minWidth: 110, fontSize: 12, '& .MuiSelect-select': { py: 0.25 } }}
      >
        <MenuItem value="" disabled sx={{ fontSize: 12 }}>加载模板</MenuItem>
        {templates.map(t => (
          <MenuItem key={t.id} value={String(t.id)} sx={{ fontSize: 12 }}>{t.name}</MenuItem>
        ))}
      </Select>
      <Tooltip title="导出 YAML 文件">
        <IconButton size="small" onClick={handleExportYaml}>
          <DownloadIcon fontSize="small" />
        </IconButton>
      </Tooltip>
      <Tooltip title="设置">
        <IconButton size="small"><SettingsIcon fontSize="small" /></IconButton>
      </Tooltip>
      <Button size="small" variant="contained" onClick={handleRun}
        sx={{ bgcolor: colors.success, '&:hover': { bgcolor: '#4caf50' } }}>
        ▶ 运行
      </Button>
      <Button size="small" variant="contained" onClick={handleStop}
        sx={{ bgcolor: colors.danger, '&:hover': { bgcolor: '#d32f2f' } }}>
        ■ 停止
      </Button>
      <Tooltip title="添加规则">
        <IconButton size="small" onClick={() => addRule()}><AddIcon fontSize="small" /></IconButton>
      </Tooltip>
      <Tooltip title="清空全部规则">
        <IconButton size="small" onClick={clearAll}><DeleteIcon fontSize="small" /></IconButton>
      </Tooltip>
    </Box>
  )
}
