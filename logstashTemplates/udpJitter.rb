def filter(event)
    sd = Array.new, ds = Array.new, mos = Array.new, icmpf = Array.new
    operations = event.to_hash["operations"]
    ip = event.to_hash["ip"]
    sd.clear, ds.clear, mos.clear, icmpf.clear
    event.to_hash.each { |k, v|
        if (operations.include? k[-1]) and k[-4] == "2" and k[-3] == "6" then
            event.remove(k)
            event.set(ip+"_PacketLossSD_"+k[-1], v)
            sd << v
        elsif (operations.include? k[-1]) and k[-4] == "2" and k[-3] == "7"
            event.remove(k)
            event.set(ip+"_PacketLossDS_"+k[-1], v)
            ds << v
        elsif (operations.include? k[-1]) and k[-4] == "4" and k[-3] == "2"
            event.remove(k)
            event.set(ip+"_MOS_"+k[-1], v.to_f)
            mos << v
        elsif (operations.include? k[-1]) and k[-4] == "4" and k[-3] == "3"
            event.remove(k)
            event.set(ip+"_ICMPF_"+k[-1], v)
            icmpf << v
        elsif k == "@timestamp"
            event.remove(k)
            event.set(k, v)
        else
            event.remove(k)
        end
    }
    if sd.size > 0 then
        event.set(ip+"_PacketLossSD", sd.sum(0.0)/sd.size)
    end
    if ds.size > 0 then
        event.set(ip+"_PacketLossDS", ds.sum(0.0)/ds.size)
    end
    if mos.size > 0 then
        event.set(ip+"_MOS", mos.sum(0.0)/mos.size)
    end
    if icmpf.size > 0 then
        event.set(ip+"_ICMPF", icmpf.sum(0.0)/icmpf.size)
    end
    return[event]
end
