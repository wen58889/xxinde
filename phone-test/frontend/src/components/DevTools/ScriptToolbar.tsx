import { Box, Button, IconButton, Tooltip, Select, MenuItem, Dialog, DialogTitle, DialogContent, DialogActions, TextField, List, ListItem, ListItemText, ListItemIcon, Typography } from '@mui/material'
import SettingsIcon from '@mui/icons-material/Settings'
import AddIcon from '@mui/icons-material/Add'
import DeleteIcon from '@mui/icons-material/Delete'
import FolderOpenIcon from '@mui/icons-material/FolderOpen'
import DownloadIcon from '@mui/icons-material/Download'
import SaveIcon from '@mui/icons-material/Save'
import DescriptionIcon from '@mui/icons-material/Description'
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline'
import UploadFileIcon from '@mui/icons-material/UploadFile'
import { useState, useEffect, useRef } from 'react'
import { useRuleStore } from '../../stores/ruleStore'
import { useLogStore } from '../../stores/logStore'
import { templatesApi, tasksApi, devicesApi, emergencyApi } from '../../api/devices'
import { useDeviceStore } from '../../stores/deviceStore'
import { colors } from '../../theme'
import { rulesToYaml, yamlToRules } from '../../utils/rulesYaml'

export default function ScriptToolbar() {
  const rules = useRuleStore((s) => s.rules)
  const addRule = useRuleStore((s) => s.addRule)
  const clearAll = useRuleStore((s) => s.clearAll)
  const loadRules = useRuleStore((s) => s.loadRules)
  const addLog = useLogStore((s) => s.addLog)
  const selectedDeviceId = useDeviceStore((s) => s.selectedDeviceId)

  const [templates, setTemplates] = useState<{ id: number; name: string; yaml_content: string; app_name?: string; version?: number; created_at?: string }[]>([])
  const [selectedTplId, setSelectedTplId] = useState<number | null>(null)
  const [scriptName, setScriptName] = useState('')
  const [saveDialogOpen, setSaveDialogOpen] = useState(false)
  const [loadDialogOpen, setLoadDialogOpen] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const refreshTemplates = () => {
    templatesApi.list()
      .then((list: any[]) => setTemplates(list))
      .catch(() => {})
  }

  useEffect(() => { refreshTemplates() }, [])

  const getScriptName = () => {
    if (selectedTplId) {
      const tpl = templates.find(t => t.id === selectedTplId)
      return tpl?.name || ''
    }
    return ''
  }

  const handleSaveClick = () => {
    setScriptName(getScriptName())
    setSaveDialogOpen(true)
    setTimeout(() => inputRef.current?.select(), 100)
  }

  const handleSaveConfirm = async () => {
    const name = scriptName.trim()
    if (!name) {
      addLog('脚本名称不能为空', 'warn')
      return
    }
    try {
      if (selectedTplId) {
        const tpl = templates.find(t => t.id === selectedTplId)
        await templatesApi.update(selectedTplId, {
          app_name: tpl?.app_name || 'default',
          name,
          yaml_content: JSON.stringify(rules),
        })
        addLog(`脚本已更新: ${name}`, 'success')
      } else {
        const res = await templatesApi.create({
          app_name: 'default',
          name,
          yaml_content: JSON.stringify(rules),
        }) as any
        setSelectedTplId(res.id)
        addLog(`脚本已保存: ${name}`, 'success')
      }
      setSaveDialogOpen(false)
      refreshTemplates()
    } catch (e) {
      addLog(`保存失败: ${e}`, 'error')
    }
  }

  const handleLoadTemplate = (id: number) => {
    setSelectedTplId(id)
    const tpl = templates.find(t => t.id === id)
    if (!tpl) return
    try {
      const parsed = JSON.parse(tpl.yaml_content)
      if (Array.isArray(parsed)) {
        loadRules(parsed)
        addLog(`已加载模板: ${tpl.name}`, 'success')
        setLoadDialogOpen(false)
        return
      }
    } catch {}
    try {
      const rules = yamlToRules(tpl.yaml_content)
      if (rules.length > 0) {
        loadRules(rules)
        addLog(`已加载YAML模板: ${tpl.name} (${rules.length}步)`, 'success')
        setLoadDialogOpen(false)
        return
      }
    } catch {}
    addLog('模板格式不兼容', 'error')
  }

  const handleDeleteTemplate = async (id: number) => {
    try {
      await templatesApi.delete(id)
      if (selectedTplId === id) setSelectedTplId(null)
      addLog('脚本已删除', 'success')
      refreshTemplates()
    } catch (e) {
      addLog(`删除失败: ${e}`, 'error')
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

      if (msg.includes('ESTOP')) {
        addLog(`设备急停中，自动复位并重试...`, 'warn')
        try {
          await devicesApi.reset(selectedDeviceId)
          addLog('复位指令已发送，等待恢复(5s)...', 'warn')
          await new Promise(r => setTimeout(r, 5000))
          const yaml = rulesToYaml(rules)
          const res = await tasksApi.runYaml(selectedDeviceId, yaml) as any
          addLog(`复位成功，任务已提交 #${res.id}`, 'success')
        } catch (e2: any) {
          const msg2 = e2?.response?.data?.detail || (e2 instanceof Error ? e2.message : String(e2))
          addLog(`复位后仍无法运行: ${msg2}，请手动点击"复位"按钮`, 'error')
        }
      } else if (msg.includes('not ONLINE')) {
        addLog(`设备未就绪: ${msg}，请等待设备恢复ONLINE后重试`, 'error')
      } else {
        addLog(`运行失败: ${msg}`, 'error')
      }
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
    const currentName = selectedTplId ? (templates.find(t => t.id === selectedTplId)?.name || '') : ''
    a.download = `${currentName || 'flow'}_${Date.now()}.yaml`
    a.click()
    URL.revokeObjectURL(url)
    addLog('已导出 YAML 文件', 'success')
  }

  const handleExportJson = () => {
    const json = JSON.stringify(rules, null, 2)
    const blob = new Blob([json], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    const currentName = selectedTplId ? (templates.find(t => t.id === selectedTplId)?.name || '') : ''
    a.download = `${currentName || 'flow'}_${Date.now()}.json`
    a.click()
    URL.revokeObjectURL(url)
    addLog('已导出 JSON 文件', 'success')
  }

  const handleImportFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = (evt) => {
      const text = evt.target?.result as string
      if (!text) { addLog('文件读取失败', 'error'); return }
      const fileName = file.name.replace(/\.(json|yaml|yml)$/i, '')
      if (file.name.endsWith('.json')) {
        try {
          const parsed = JSON.parse(text)
          if (Array.isArray(parsed)) {
            loadRules(parsed)
            setSelectedTplId(null)
            addLog(`已导入脚本: ${fileName}`, 'success')
            setLoadDialogOpen(false)
          } else {
            addLog('JSON 文件格式不正确，需要规则数组', 'error')
          }
        } catch {
          addLog('JSON 文件解析失败', 'error')
        }
      } else if (file.name.endsWith('.yaml') || file.name.endsWith('.yml')) {
        try {
          const parsedRules = yamlToRules(text)
          if (parsedRules.length > 0) {
            loadRules(parsedRules)
            setSelectedTplId(null)
            addLog(`已导入 YAML 脚本: ${fileName} (${parsedRules.length}步)`, 'success')
            setLoadDialogOpen(false)
          } else {
            addLog('YAML 文件中未找到有效步骤', 'error')
          }
        } catch (err) {
          addLog(`YAML 解析失败: ${err}`, 'error')
        }
      } else {
        addLog('不支持的文件格式，请使用 .json 或 .yaml 文件', 'error')
      }
    }
    reader.onerror = () => addLog('文件读取失败', 'error')
    reader.readAsText(file)
    e.target.value = ''
  }

  return (
    <Box sx={{ display: 'flex', gap: 0.5, alignItems: 'center', flexWrap: 'wrap' }}>
      <Button size="small" variant="contained" startIcon={<SaveIcon />} onClick={handleSaveClick}
        sx={{ bgcolor: colors.success, '&:hover': { bgcolor: '#4caf50' } }}>
        保存
      </Button>
      <Select
        size="small"
        value={selectedTplId ?? ''}
        onChange={(e) => {
          const v = e.target.value
          if (v === '') { setSelectedTplId(null); return }
          handleLoadTemplate(Number(v))
        }}
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
      <Tooltip title="导出 YAML">
        <IconButton size="small" onClick={handleExportYaml}>
          <DownloadIcon fontSize="small" />
        </IconButton>
      </Tooltip>
      <Tooltip title="导出 JSON">
        <IconButton size="small" onClick={handleExportJson}
          sx={{ '& .MuiSvgIcon-root': { fontSize: 18 } }}>
          <DownloadIcon fontSize="small" sx={{ color: '#81c784' }} />
        </IconButton>
      </Tooltip>
      <Tooltip title="脚本管理">
        <IconButton size="small" onClick={() => { refreshTemplates(); setLoadDialogOpen(true) }}><SettingsIcon fontSize="small" /></IconButton>
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
        <IconButton size="small" onClick={() => { clearAll(); setSelectedTplId(null) }}><DeleteIcon fontSize="small" /></IconButton>
      </Tooltip>

      {/* 保存对话框 */}
      <Dialog open={saveDialogOpen} onClose={() => setSaveDialogOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>{selectedTplId ? '保存脚本' : '新建脚本'}</DialogTitle>
        <DialogContent>
          <TextField
            inputRef={inputRef}
            autoFocus
            margin="dense"
            label="脚本名称"
            fullWidth
            value={scriptName}
            onChange={(e) => setScriptName(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleSaveConfirm() }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSaveDialogOpen(false)}>取消</Button>
          <Button variant="contained" onClick={handleSaveConfirm}
            sx={{ bgcolor: colors.success, '&:hover': { bgcolor: '#4caf50' } }}>
            保存
          </Button>
        </DialogActions>
      </Dialog>

      {/* 脚本管理对话框 */}
      <Dialog open={loadDialogOpen} onClose={() => setLoadDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>脚本管理</DialogTitle>
        <DialogContent>
          <Box sx={{ mb: 1.5, display: 'flex', justifyContent: 'flex-end' }}>
            <Button
              size="small"
              variant="outlined"
              startIcon={<UploadFileIcon />}
              onClick={() => fileInputRef.current?.click()}
              sx={{ textTransform: 'none' }}
            >
              导入文件
            </Button>
            <input
              ref={fileInputRef}
              type="file"
              accept=".json,.yaml,.yml"
              style={{ display: 'none' }}
              onChange={handleImportFile}
            />
          </Box>
          {templates.length === 0 ? (
            <Typography sx={{ py: 2, textAlign: 'center', color: '#888' }}>
              暂无已保存的脚本
            </Typography>
          ) : (
            <List disablePadding>
              {templates.map((t) => (
                <ListItem
                  key={t.id}
                  sx={{
                    bgcolor: selectedTplId === t.id ? '#1a2a4e' : 'transparent',
                    borderRadius: 1,
                    mb: 0.5,
                    border: selectedTplId === t.id ? `1px solid ${colors.highlight}` : '1px solid #333',
                    cursor: 'pointer',
                    '&:hover': { bgcolor: '#1a2a4e' },
                  }}
                  onClick={() => handleLoadTemplate(t.id)}
                >
                  <ListItemIcon sx={{ minWidth: 32 }}>
                    <DescriptionIcon sx={{ fontSize: 20, color: selectedTplId === t.id ? colors.highlight : '#888' }} />
                  </ListItemIcon>
                  <ListItemText
                    primary={
                      <Typography sx={{ fontSize: 13, fontWeight: selectedTplId === t.id ? 600 : 400, color: selectedTplId === t.id ? colors.highlight : '#e0e0e0' }}>
                        {t.name}
                      </Typography>
                    }
                    secondary={
                      <Typography sx={{ fontSize: 11, color: '#888' }}>
                        {t.app_name || 'default'} · v{t.version ?? 1}{t.created_at ? ` · ${new Date(t.created_at).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}` : ''}
                      </Typography>
                    }
                  />
                  <IconButton
                    size="small"
                    onClick={(e) => { e.stopPropagation(); handleDeleteTemplate(t.id) }}
                    sx={{ color: '#888', '&:hover': { color: colors.danger } }}
                  >
                    <DeleteOutlineIcon sx={{ fontSize: 18 }} />
                  </IconButton>
                </ListItem>
              ))}
            </List>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setLoadDialogOpen(false)}>关闭</Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
