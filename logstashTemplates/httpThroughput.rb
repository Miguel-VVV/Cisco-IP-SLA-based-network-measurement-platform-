def filter(event)
    calc = false
    time = 0
    body = 0
    operation = event.to_hash["operations"]
    ip = event.to_hash["ip"]
    event.to_hash.each { |k, v|
        if operation == k[-1] then
            calc = true
            if k[-3] == "4" then
                time = v.to_f/1000
                event.remove(k)
                event.set(ip+"_Transaction_RTT", time)
            elsif k[-3] == "5"
                body = v*8
                event.remove(k)
                event.set(ip+"_Body", body)
            else
                event.remove(k)
            end
        elsif k == "@timestamp"
            event.remove(k)
            event.set(k, v)
        else
            event.remove(k)
        end
    }
    if calc then
        throughput = body/time
        event.set(ip+"_Throughput", throughput)
    end
    return[event]
end
