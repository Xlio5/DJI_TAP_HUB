package com.tunnathub.app;

import com.tunnathub.app.rc.GetEventRcReaderTest;
import com.tunnathub.app.rc.Port40007RcReaderTest;
import com.tunnathub.app.rc.RcFusionEngineTest;
import com.tunnathub.app.rc.RcMsgCodecTest;
import com.tunnathub.app.video.H264AccessUnitAssemblerTest;
import com.tunnathub.app.video.RtcpFeedbackTest;
import com.tunnathub.app.video.RtspKeyFrameRequesterTest;
import com.tunnathub.app.video.RtspPlaybackEngineTest;
import com.tunnathub.app.video.RtspUdpProbeParserTest;
import com.tunnathub.app.video.UdpLowLatencyPolicyTest;

import org.easydarwin.video.BenchmarkStatsTest;
import org.easydarwin.video.CodecNameRankerTest;
import org.junit.Test;

/** 让现有 main() 断言测试进入标准 Gradle/JUnit 测试生命周期。 */
public final class AllMainTests {
    @Test public void autoStartPolicy() { AutoStartPolicyTest.main(new String[0]); }
    @Test public void channelConfigWorkbench() { ChannelConfigWorkbenchTest.main(new String[0]); }
    @Test public void rcInputMode() { RcInputModeTest.main(new String[0]); }
    @Test public void rcMsgUiPump() { RcMsgUiPumpTest.main(new String[0]); }
    @Test public void rcStickMapper() { RcStickMapperTest.main(new String[0]); }
    @Test public void getEventRcReader() { GetEventRcReaderTest.main(new String[0]); }
    @Test public void port40007RcReader() { Port40007RcReaderTest.main(new String[0]); }
    @Test public void rcFusionEngine() { RcFusionEngineTest.main(new String[0]); }
    @Test public void rcMsgCodec() { RcMsgCodecTest.main(new String[0]); }
    @Test public void h264AccessUnitAssembler() { H264AccessUnitAssemblerTest.main(new String[0]); }
    @Test public void rtcpFeedback() { RtcpFeedbackTest.main(new String[0]); }
    @Test public void rtspKeyFrameRequester() { RtspKeyFrameRequesterTest.main(new String[0]); }
    @Test public void rtspPlaybackEngine() { RtspPlaybackEngineTest.main(new String[0]); }
    @Test public void rtspUdpProbeParser() { RtspUdpProbeParserTest.main(new String[0]); }
    @Test public void udpLowLatencyPolicy() { UdpLowLatencyPolicyTest.main(new String[0]); }
    @Test public void benchmarkStats() { BenchmarkStatsTest.main(new String[0]); }
    @Test public void codecNameRanker() { CodecNameRankerTest.main(new String[0]); }
}
