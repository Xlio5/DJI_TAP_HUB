/** UDP ping - one-shot via app_process on DJI RC */
import java.net.*;
import java.nio.ByteBuffer;

public class UdpPing {
    public static void main(String[] args) throws Exception {
        int n = 100;
        DatagramSocket s = new DatagramSocket();
        s.setSoTimeout(3000);
        InetSocketAddress server = new InetSocketAddress("10.0.0.1", 9999);

        double[] rtts = new double[n];
        int drp = 0;
        ByteBuffer bb = ByteBuffer.allocate(32);

        for (int i = 0; i < n; i++) {
            bb.clear();
            long t0 = System.nanoTime();
            bb.putLong(t0);
            DatagramPacket pkt = new DatagramPacket(bb.array(), bb.position(), server);
            s.send(pkt);
            try {
                DatagramPacket resp = new DatagramPacket(new byte[256], 256);
                s.receive(resp);
                long t1 = System.nanoTime();
                ByteBuffer rb = ByteBuffer.wrap(resp.getData());
                long sent = rb.getLong();
                double rtt = (t1 - sent) / 1_000_000.0;
                rtts[i - drp] = rtt;
            } catch (SocketTimeoutException e) {
                drp++;
            }
        }
        s.close();

        java.util.Arrays.sort(rtts, 0, n - drp);
        double sum = 0;
        for (int i = 0; i < n - drp; i++) sum += rtts[i];
        double avg = sum / (n - drp);
        int i50 = (n - drp) / 2;
        int i95 = (int)((n - drp) * 0.95);
        int i99 = (n - drp) > 50 ? (int)((n - drp) * 0.99) : (n - drp) - 1;
        System.out.printf("RESULT n=%d drp=%d avg=%.2f p50=%.2f p95=%.2f p99=%.2f min=%.2f max=%.2f%n",
            n, drp, avg, rtts[i50], rtts[i95], rtts[i99], rtts[0], rtts[(n-drp)-1]);
    }
}
