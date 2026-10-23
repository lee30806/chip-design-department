"""axis_crc_append 동결 RTL(674c)의 DV 공백: stat_frames 16비트 롤오버(CRC-08)와 SVA 실행."""
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, ReadOnly, RisingEdge


async def reset(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.rst.value = 1
    dut.s_axis_tvalid.value = 0
    dut.s_axis_tdata.value = 0
    dut.s_axis_tlast.value = 0
    dut.s_axis_tuser.value = 0
    dut.m_axis_tready.value = 1
    await ClockCycles(dut.clk, 5)
    await FallingEdge(dut.clk)
    dut.rst.value = 0


async def send(dut, data, last):
    """하강 에지에서 구동하고, 다음 상승 에지 직전의 ready로 전송 여부를 판정한다 (상승 에지 뒤의 ready를 보면 틀림)."""
    dut.s_axis_tdata.value = data
    dut.s_axis_tlast.value = last
    dut.s_axis_tvalid.value = 1
    while True:
        await ReadOnly()
        rdy = int(dut.s_axis_tready.value)
        await RisingEdge(dut.clk)
        await FallingEdge(dut.clk)
        if rdy:
            break
    dut.s_axis_tvalid.value = 0


async def one_byte_frame(dut, data):
    await send(dut, data, 1)


@cocotb.test()
async def stat_frames_rollover(dut):
    """CRC-08: 0xFFFF 다음은 0. 1바이트 프레임 65537개를 보내 stat_frames가 0xFFFF → 0 → 1이 되는지 본다."""
    await reset(dut)
    seen = []
    for i in range(65537):
        await one_byte_frame(dut, i & 0xFF)
        if i in (65534, 65535, 65536):
            await ClockCycles(dut.clk, 12)   # CRC 두 바이트가 나가고 stat_frames가 늘 때까지
            await ReadOnly()
            seen.append(int(dut.stat_frames.value))
            await FallingEdge(dut.clk)
    assert seen == [0xFFFF, 0, 1], seen


@cocotb.test()
async def stalls_and_mid_reset(dut):
    """SVA a_hold, a_rst가 실제로 도는 자극: backpressure를 섞고 프레임 도중 리셋."""
    await reset(dut)

    async def ready_pattern():
        k = 0
        while True:
            await FallingEdge(dut.clk)
            dut.m_axis_tready.value = (k % 3) != 1
            k += 1
    cocotb.start_soon(ready_pattern())
    for f in range(20):
        for b in range(5):
            await send(dut, (f * 7 + b) & 0xFF, int(b == 4))
            if f == 10 and b == 2:
                dut.rst.value = 1
                await ClockCycles(dut.clk, 2)
                await FallingEdge(dut.clk)
                dut.rst.value = 0
        dut.s_axis_tvalid.value = 0
    await ClockCycles(dut.clk, 20)



@cocotb.test()
async def first_frame_after_mid_reset(dut):
    """CRC-E03, CRC-E04: 프레임 도중 리셋 뒤에는 끊긴 프레임의 남은 바이트나 CRC가 나오지 않고, 다음 프레임은 처음부터 맞게 나간다."""
    await reset(dut)
    for b in (0xA5, 0x5A, 0x11):   # tlast 없이 끊길 프레임
        await send(dut, b, 0)
    dut.rst.value = 1
    await ClockCycles(dut.clk, 2)
    await FallingEdge(dut.clk)
    dut.rst.value = 0
    out = []

    async def monitor():   # 리셋이 풀린 뒤의 하강 에지부터: 이 표본의 valid/ready로 다음 상승 에지 전송을 판정
        while True:
            await ReadOnly()
            if int(dut.m_axis_tvalid.value) and int(dut.m_axis_tready.value):
                out.append((int(dut.m_axis_tdata.value), int(dut.m_axis_tlast.value), int(dut.m_axis_tuser.value)))
            await FallingEdge(dut.clk)
    cocotb.start_soon(monitor())
    msg = list(range(0x31, 0x3A))
    for i, b in enumerate(msg):
        await send(dut, b, int(i == len(msg) - 1))
    await ClockCycles(dut.clk, 12)
    await ReadOnly()
    want = [(b, 0, 0) for b in msg] + [(0x29, 0, 0), (0xB1, 1, 0)]
    assert out == want, out
    assert int(dut.stat_frames.value) == 1
