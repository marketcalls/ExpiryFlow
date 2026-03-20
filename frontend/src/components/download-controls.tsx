import { useEffect, useState } from "react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Spinner } from "@/components/ui/spinner"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { downloadsApi } from "@/api/downloads"
import { useDownloadStore } from "@/store/download-store"
import { ApiError } from "@/api/client"
import { request } from "@/api/client"

interface UnderlyingMeta {
  security_id: number
  exchange_segment: string
  instrument: string
  strike_step: number
}

const OPTION_TYPES = ["CALL", "PUT", "BOTH"]
const EXPIRY_FLAGS = [
  { value: "WEEK", label: "Weekly" },
  { value: "MONTH", label: "Monthly" },
]
const EXPIRY_CODES = [
  { value: 1, label: "Current" },
  { value: 2, label: "Next" },
  { value: 3, label: "Far" },
]
const INTERVALS = [
  { value: "1", label: "1 min" },
  { value: "5", label: "5 min" },
  { value: "15", label: "15 min" },
  { value: "25", label: "25 min" },
  { value: "60", label: "60 min" },
]

const PRESETS = [
  { label: "1M", months: 1 },
  { label: "3M", months: 3 },
  { label: "6M", months: 6 },
  { label: "1Y", months: 12 },
  { label: "2Y", months: 24 },
  { label: "3Y", months: 36 },
  { label: "5Y", months: 60 },
]

function subtractMonths(dateStr: string, months: number): string {
  const d = dateStr ? new Date(dateStr) : new Date()
  d.setMonth(d.getMonth() - months)
  return d.toISOString().split("T")[0]
}

function toggleArray<T>(arr: T[], item: T): T[] {
  return arr.includes(item) ? arr.filter((v) => v !== item) : [...arr, item]
}

export function DownloadControls() {
  const { setActiveJob, isDownloading } = useDownloadStore()
  const [isPending, setIsPending] = useState(false)
  const [underlyings, setUnderlyings] = useState<Record<string, UnderlyingMeta>>({})
  const [form, setForm] = useState(() => {
    const today = new Date()
    const weekAgo = new Date(today)
    weekAgo.setDate(weekAgo.getDate() - 7)
    return {
      underlying_scrip: "NIFTY",
      option_type: "BOTH",
      expiry_flags: ["MONTH"] as string[],
      expiry_codes: [1] as number[],
      strike_range: "10",
      interval: "1",
      from_date: weekAgo.toISOString().split("T")[0],
      to_date: today.toISOString().split("T")[0],
    }
  })

  useEffect(() => {
    async function fetchMeta() {
      try {
        const result = await request<{ underlyings: Record<string, UnderlyingMeta> }>("/underlyings")
        setUnderlyings(result.underlyings)
      } catch {
        // fallback
      }
    }
    fetchMeta()
  }, [])

  const selectedMeta = underlyings[form.underlying_scrip]
  const underlyingKeys = Object.keys(underlyings)

  const totalStrikes = (parseInt(form.strike_range) || 0) * 2 + 1
  const optionCount = form.option_type === "BOTH" ? 2 : 1
  const expiryComboCount = form.expiry_flags.length * form.expiry_codes.length
  const totalApiCalls = totalStrikes * optionCount * expiryComboCount

  const applyPreset = (months: number) => {
    const toDate = form.to_date || new Date().toISOString().split("T")[0]
    setForm({
      ...form,
      to_date: toDate,
      from_date: subtractMonths(toDate, months),
    })
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!form.from_date || !form.to_date) {
      toast.error("From and To dates are required")
      return
    }

    if (!selectedMeta) {
      toast.error("Invalid underlying selected")
      return
    }

    if (form.expiry_flags.length === 0) {
      toast.error("Select at least one expiry type")
      return
    }

    if (form.expiry_codes.length === 0) {
      toast.error("Select at least one expiry code")
      return
    }

    setIsPending(true)
    try {
      const result = await downloadsApi.start({
        underlying_scrip: form.underlying_scrip,
        exchange_segment: selectedMeta.exchange_segment,
        instrument: selectedMeta.instrument,
        security_id: selectedMeta.security_id,
        option_type: form.option_type,
        expiry_flags: form.expiry_flags,
        expiry_codes: form.expiry_codes,
        strike_range: parseInt(form.strike_range),
        interval: form.interval,
        from_date: form.from_date,
        to_date: form.to_date,
      })
      setActiveJob(result)
      toast.success(`Download started: ~${totalApiCalls} API calls`)
    } catch (err) {
      if (err instanceof ApiError) {
        toast.error(err.detail)
      } else {
        toast.error("Failed to start download")
      }
    } finally {
      setIsPending(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Download Expired Options Data</CardTitle>
        <CardDescription>
          Fetch historical OHLCV data for expired option contracts from Dhan.
          Strikes are relative to ATM (-N to +N).
        </CardDescription>
      </CardHeader>
      <form onSubmit={handleSubmit}>
        <CardContent>
          <FieldGroup>
            <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
              <Field>
                <FieldLabel>Underlying</FieldLabel>
                <Select
                  value={form.underlying_scrip}
                  onValueChange={(v) => setForm({ ...form, underlying_scrip: v })}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      {underlyingKeys.map((u) => (
                        <SelectItem key={u} value={u}>{u}</SelectItem>
                      ))}
                    </SelectGroup>
                  </SelectContent>
                </Select>
                {selectedMeta && (
                  <FieldDescription>
                    {selectedMeta.exchange_segment} / ID: {selectedMeta.security_id}
                  </FieldDescription>
                )}
              </Field>
              <Field>
                <FieldLabel>Option Type</FieldLabel>
                <Select
                  value={form.option_type}
                  onValueChange={(v) => setForm({ ...form, option_type: v })}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      {OPTION_TYPES.map((o) => (
                        <SelectItem key={o} value={o}>{o}</SelectItem>
                      ))}
                    </SelectGroup>
                  </SelectContent>
                </Select>
              </Field>
            </div>

            <div className="grid grid-cols-1 gap-5 sm:grid-cols-3">
              <Field>
                <FieldLabel>Expiry Type</FieldLabel>
                <div className="flex flex-col gap-2 pt-1">
                  {EXPIRY_FLAGS.map((f) => (
                    <label key={f.value} className="flex items-center gap-2 text-sm">
                      <Checkbox
                        checked={form.expiry_flags.includes(f.value)}
                        onCheckedChange={() =>
                          setForm({
                            ...form,
                            expiry_flags: toggleArray(form.expiry_flags, f.value),
                          })
                        }
                      />
                      {f.label}
                    </label>
                  ))}
                </div>
              </Field>
              <Field>
                <FieldLabel>Expiry</FieldLabel>
                <div className="flex flex-col gap-2 pt-1">
                  {EXPIRY_CODES.map((c) => (
                    <label key={c.value} className="flex items-center gap-2 text-sm">
                      <Checkbox
                        checked={form.expiry_codes.includes(c.value)}
                        onCheckedChange={() =>
                          setForm({
                            ...form,
                            expiry_codes: toggleArray(form.expiry_codes, c.value),
                          })
                        }
                      />
                      {c.label}
                    </label>
                  ))}
                </div>
              </Field>
              <Field>
                <FieldLabel htmlFor="strike_range">Strike Range (+/-)</FieldLabel>
                <Input
                  id="strike_range"
                  type="number"
                  min="0"
                  max="20"
                  value={form.strike_range}
                  onChange={(e) => setForm({ ...form, strike_range: e.target.value })}
                />
                <FieldDescription>
                  {totalStrikes} strikes x {expiryComboCount} expiry combo(s) = ~{totalApiCalls} API calls
                </FieldDescription>
              </Field>
            </div>

            <Field>
              <FieldLabel>Interval</FieldLabel>
              <Select
                value={form.interval}
                onValueChange={(v) => setForm({ ...form, interval: v })}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    {INTERVALS.map((i) => (
                      <SelectItem key={i.value} value={i.value}>{i.label}</SelectItem>
                    ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
            </Field>

            <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
              <Field>
                <FieldLabel htmlFor="from_date">From Date</FieldLabel>
                <Input
                  id="from_date"
                  type="date"
                  value={form.from_date}
                  onChange={(e) => setForm({ ...form, from_date: e.target.value })}
                />
              </Field>
              <Field>
                <FieldLabel htmlFor="to_date">To Date</FieldLabel>
                <Input
                  id="to_date"
                  type="date"
                  value={form.to_date}
                  onChange={(e) => setForm({ ...form, to_date: e.target.value })}
                />
              </Field>
            </div>

            <div className="flex flex-col gap-2">
              <span className="text-sm text-muted-foreground">Quick presets (sets From Date)</span>
              <div className="flex flex-wrap gap-2">
                {PRESETS.map((p) => (
                  <Button
                    key={p.label}
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => applyPreset(p.months)}
                  >
                    {p.label}
                  </Button>
                ))}
              </div>
            </div>

          </FieldGroup>
        </CardContent>
        <CardFooter>
          <Button
            type="submit"
            className="w-full"
            disabled={isPending || isDownloading()}
          >
            {isPending && <Spinner data-icon="inline-start" />}
            {isDownloading() ? "Download in progress..." : "Download Data"}
          </Button>
        </CardFooter>
      </form>
    </Card>
  )
}
